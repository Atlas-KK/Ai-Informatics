import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import text

from ai_intel.api.app import create_app
from ai_intel.application.archive import ArchiveService
from ai_intel.application.daily_selection import DailySelectionService
from ai_intel.application.delivery import NoFailedDeliverySegmentsError
from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.application.intelligence_processing import (
    IntelligenceProcessingService,
    ProcessingOutcome,
)
from ai_intel.application.search import ExternalSearchHit, SearchDocument
from ai_intel.config import Settings
from ai_intel.domain.models import ArchiveCandidate, EvidenceInput, ScoreInput
from ai_intel.domain.pipeline import DeliveryRetryResult
from ai_intel.domain.source import CollectedItem, CollectionStatus, SourceType
from ai_intel.domain.states import Tier
from ai_intel.foundation import close_runtime, initialize_runtime
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter
from ai_intel.infrastructure.db.engine import create_sqlite_engine
from ai_intel.infrastructure.db.migrations import upgrade_database
from ai_intel.infrastructure.db.schema import (
    aggregate_versions,
    ai_processing_results,
    candidate_scores,
    daily_digests,
    daily_selection_runs,
    delivery_segments,
    event_aggregates,
    event_versions,
    events,
    evidence,
    formalization_links,
    pipeline_runs,
    pipeline_work_items,
    scores,
    staged_commits,
    telemetry_events,
    user_metadata,
)
from ai_intel.infrastructure.vault_projection.projector import VaultProjector
from ai_intel.ports.llm import LLMOperation, LLMRequest

EVENT_ID = "70000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 9, 4, 1, tzinfo=UTC)


class FakeSemanticRanker:
    def rank(self, query: str, documents: Sequence[SearchDocument]) -> Mapping[str, float]:
        return {document.event_id: 0.9 for document in documents if query == "智能助手"}


class FakeExpansionProvider:
    def search(self, query: str) -> Sequence[ExternalSearchHit]:
        return (
            ExternalSearchHit(
                title=f"Extended {query}",
                url="https://external.example.test/new-agent",
                summary="A relevant external result.",
                content="External result content retained only after favorite.",
                source_name="external-fixture",
                score=88,
            ),
        )


class UnsafeExpansionProvider:
    def search(self, query: str) -> Sequence[ExternalSearchHit]:
        return (
            ExternalSearchHit(
                title=query,
                url="javascript:alert('unsafe')",
                summary="unsafe URL must never reach the UI",
                content="unsafe",
                source_name="unsafe-fixture",
                score=100,
            ),
        )


class ExtensionProcessingLLM:
    def complete(self, request: LLMRequest) -> str:
        evidence_id = str(request.context["evidence_ids"][0])
        if request.operation is LLMOperation.GENERATE_TOPIC_IDEA:
            return json.dumps(
                {
                    "schema_version": "phase5.topic_idea.v1",
                    "title": "扩展结果背后的产品机会",
                    "outline": ["变化背景", "产品影响", "行动建议"],
                    "hook": "一个扩展信号如何改变产品判断",
                    "support_evidence_ids": [evidence_id],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "schema_version": "phase5.processing.v1",
                "source_language": "en",
                "zh_translation": "外部结果的中文译文。",
                "zh_summary": "经过正式加工的外部结果摘要。",
                "key_conclusions": [{"text": "外部结果结论", "evidence_ids": [evidence_id]}],
                "pm_value": "用于产品决策参考。",
                "primary_topic": "AI 产品形态与行业应用",
                "tags": ["扩展搜索"],
                "dimension_scores": {
                    "source_authority": 70,
                    "timeliness": 100,
                    "reach": 70,
                    "information_density": 88,
                    "innovation": 88,
                },
                "dimension_rationales": {
                    "source_authority": "公开来源默认权威度",
                    "timeliness": "当前扩展搜索结果",
                    "reach": "缺少互动数据",
                    "information_density": "摘要包含产品信息",
                    "innovation": "包含新产品观点",
                },
            },
            ensure_ascii=False,
        )


class RetryableTopicIdeaLLM(ExtensionProcessingLLM):
    fail_topic = True

    def complete(self, request: LLMRequest) -> str:
        if request.operation is LLMOperation.GENERATE_TOPIC_IDEA and self.fail_topic:
            raise TimeoutError("fixture timeout")
        return super().complete(request)


class RetryableExtensionProcessingLLM(ExtensionProcessingLLM):
    fail_processing = True

    def complete(self, request: LLMRequest) -> str:
        if request.operation is LLMOperation.PROCESS_INTELLIGENCE and self.fail_processing:
            self.fail_processing = False
            raise TimeoutError("fixture timeout")
        return super().complete(request)


def candidate() -> ArchiveCandidate:
    return ArchiveCandidate(
        event_id=EVENT_ID,
        snapshot_id="71000000-0000-4000-8000-000000000001",
        source_id="source-primary",
        canonical_title="Agent Platform launch",
        primary_topic="大模型与智能体",
        change_type="NEW",
        raw_content="Raw source snapshot.",
        content="正文安全 <script>alert('xss')</script>",
        summary="Quantum product brief.",
        evidence=(
            EvidenceInput(
                source_id="source-primary",
                url="https://example.test/agent-platform",
                published_at=NOW,
                viewpoint="Primary viewpoint",
            ),
            EvidenceInput(
                source_id="source-secondary",
                url="https://secondary.example.test/agent-platform",
                published_at=NOW,
                viewpoint="Independent viewpoint",
            ),
        ),
        score=ScoreInput(
            config_version=1,
            dimensions={"authority": 90},
            total=91,
            tier=Tier.MUST_READ,
        ),
        created_at=NOW,
    )


def seed_candidate(client: TestClient, value: ArchiveCandidate) -> None:
    runtime = client.app.state.runtime
    ArchiveService(
        runtime.repository,
        AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
        VaultProjector(runtime.data_dir, runtime.repository),
    ).commit(value)


def seed(client: TestClient) -> None:
    seed_candidate(client, candidate())


def test_p7_server_side_archive_filters_sort_and_pagination(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        primary = candidate()
        secondary = replace(
            primary,
            event_id="70000000-0000-4000-8000-000000000002",
            snapshot_id="71000000-0000-4000-8000-000000000002",
            canonical_title="Agent workflow update",
            evidence=(
                EvidenceInput(
                    source_id="source-other",
                    url="https://example.test/agent-workflow",
                    published_at=NOW + timedelta(hours=1),
                    viewpoint="Secondary product viewpoint",
                ),
            ),
            score=replace(primary.score, total=75, tier=Tier.IMPORTANT),
            created_at=NOW + timedelta(hours=1),
        )
        seed_candidate(client, primary)
        seed_candidate(client, secondary)
        client.patch(
            f"/api/archive/{EVENT_ID}/metadata",
            json={"favorite": True, "read_state": "READ"},
        )

        response = client.get(
            "/api/archive",
            params={
                "paged": "true",
                "topic": "大模型与智能体",
                "tier": "MUST_READ",
                "source": "source-primary",
                "favorite": "true",
                "read_state": "READ",
                "date_from": "2026-09-04",
                "date_to": "2026-09-04",
                "min_score": "80",
                "sort": "SCORE_DESC",
                "page": "1",
                "page_size": "1",
            },
        )
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == 1
        assert page["items"][0]["event_id"] == EVENT_ID
        assert page["page"] == 1
        assert page["page_size"] == 1

        sorted_page = client.get(
            "/api/archive",
            params={"paged": "true", "sort": "SCORE_DESC", "page_size": "1"},
        ).json()
        assert sorted_page["total"] == 2
        assert sorted_page["items"][0]["quality_score"] == 91

        legacy_read = client.get("/api/archive", params={"read_state": "READ"})
        assert legacy_read.status_code == 200
        assert [item["event_id"] for item in legacy_read.json()] == [EVENT_ID]

        legacy_unread = client.get("/api/archive", params={"read_state": "UNREAD"})
        assert legacy_unread.status_code == 200
        assert [item["event_id"] for item in legacy_unread.json()] == [secondary.event_id]

        legacy_unread_alias = client.get("/api/archive", params={"unread": "true"})
        assert legacy_unread_alias.status_code == 200
        assert [item["event_id"] for item in legacy_unread_alias.json()] == [secondary.event_id]

        for wildcard_source in ("%", "_"):
            wildcard_page = client.get(
                "/api/archive",
                params={"paged": "true", "source": wildcard_source},
            ).json()
            assert wildcard_page["total"] == 0
            assert wildcard_page["items"] == []

        no_match = client.get("/api/archive", params={"paged": "true", "tag": "missing-tag"}).json()
        assert no_match["total"] == 0
        assert no_match["items"] == []

        search = client.get(
            "/api/search",
            params={
                "q": "Agent",
                "tier": "MUST_READ",
                "source": "source-primary",
                "min_score": "80",
                "page": "1",
                "page_size": "10",
            },
        ).json()
        assert search["total"] == 1
        assert search["items"][0]["event_id"] == EVENT_ID
        assert search["degraded_reason"] == "SEMANTIC_PROVIDER_NOT_CONFIGURED"

        topics = client.get("/api/topics").json()
        assert topics["summaries"][0]["name"] == "大模型与智能体"
        assert topics["summaries"][0]["count"] == 2

        dashboard = client.get("/api/dashboard?report_date=2026-09-04").json()
        assert dashboard["today_count"] == 2
        assert dashboard["topic_summaries"][0]["count"] == 2
        assert [item["tier"] for item in dashboard["items"]] == ["MUST_READ", "IMPORTANT"]


def test_p7_dashboard_detail_search_and_user_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path), semantic_ranker=FakeSemanticRanker())
    with TestClient(app) as client:
        seed(client)

        dashboard = client.get("/api/dashboard?report_date=2026-09-04").json()
        assert dashboard["topic_counts"] == {
            "大模型与智能体": 1,
            "AI 产品形态与行业应用": 0,
            "AI 产品实战": 0,
            "AI 工程安全与可靠性": 0,
        }
        assert dashboard["tier_counts"]["MUST_READ"] == 1
        assert dashboard["total_count"] == 1
        assert dashboard["source_counts"] == {"source-primary": 1, "source-secondary": 1}
        assert dashboard["change_counts"] == {"NEW": 1, "UPDATED": 0}
        assert dashboard["seven_day_trend"]["2026-09-04"] == 1
        assert dashboard["data_complete"] is True

        detail = client.get(f"/api/archive/{EVENT_ID}")
        assert detail.status_code == 200
        payload = detail.json()
        current_version = payload["versions"][0]
        assert len(current_version["evidence"]) == 2
        assert current_version["quality_score"] == 91
        assert current_version["score_version"] == 1
        assert current_version["score_dimensions"] == payload["score_dimensions"]
        assert current_version["score_rationales"] == {}
        assert current_version["evidence"][0]["source_name"] in {
            "source-primary",
            "source-secondary",
        }
        assert current_version["evidence"][0]["coverage_percent"] is None
        assert current_version["evidence"][0]["published_at_unknown"] is None
        assert "<script>" in payload["content"]
        assert (
            client.put(f"/api/archive/{EVENT_ID}", json={"content": "changed"}).status_code == 405
        )

        assert (
            client.put(f"/api/archive/{EVENT_ID}/note", json={"body": "customer-note"}).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/archive/{EVENT_ID}/metadata",
                json={"favorite": True, "pinned": True, "read_state": "READ"},
            ).status_code
            == 200
        )

        for query in ("Agent", "Quantum", "正文安全", "source-primary", "customer-note"):
            result = client.get("/api/search", params={"q": query}).json()
            assert result["items"][0]["event_id"] == EVENT_ID
            assert result["mode"] == "HYBRID"

        runtime = client.app.state.runtime
        with runtime.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE archive_search_documents SET tags='product-tag' "
                    "WHERE event_id=:event_id"
                ),
                {"event_id": EVENT_ID},
            )
        assert (
            client.get("/api/search", params={"q": "product-tag"}).json()["items"][0]["event_id"]
            == EVENT_ID
        )

        semantic = client.get("/api/search", params={"q": "智能助手"}).json()
        assert semantic["items"][0]["event_id"] == EVENT_ID
        assert semantic["degraded"] is False

        assert (
            client.post(f"/api/archive/{EVENT_ID}/trash", json={"reason": "not useful"}).status_code
            == 200
        )
        assert client.get("/api/archive").json() == []
        assert client.get("/api/archive?trash=true").json()[0]["trash_reason"] == "not useful"
        assert client.post(f"/api/archive/{EVENT_ID}/restore").status_code == 200


def test_p7_detail_coverage_uses_normalized_viewpoint_group(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        runtime = client.app.state.runtime
        snapshot_ids: list[str] = []
        for index, viewpoint in enumerate(("Supports adoption", "supports   adoption!")):
            snapshot_id = runtime.source_repository.save_item(
                None,
                CollectedItem(
                    external_id=f"normalized-viewpoint-{index}",
                    source_id=f"normalized-source-{index}",
                    source_type=SourceType.WEB,
                    title="Shared agent release",
                    url=f"https://normalized-{index}.example.test/item",
                    author="Fixture Author",
                    published_at=NOW,
                    first_seen_at=NOW,
                    published_at_unknown=False,
                    raw_content="The shared agent release improves adoption workflows.",
                    model_input="The shared agent release improves adoption workflows.",
                    status=CollectionStatus.COLLECTED,
                    metadata={"viewpoint": viewpoint, "entities": ["Shared Agent"]},
                ),
            )
            assert snapshot_id is not None
            snapshot_ids.append(snapshot_id)

        EventAggregationService(runtime.event_repository).process_snapshot_ids(
            tuple(snapshot_ids), report_date=NOW.date(), observed_at=NOW
        )
        context = runtime.intelligence_repository.list_candidate_contexts(NOW.date())[0]
        processed = IntelligenceProcessingService(
            runtime.intelligence_repository, ExtensionProcessingLLM()
        ).process_candidate(context.aggregate_version_id, processed_at=NOW)
        assert processed.succeeded

        archive_service = ArchiveService(
            runtime.repository,
            AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
            VaultProjector(runtime.data_dir, runtime.repository),
        )
        selected = DailySelectionService(
            runtime.intelligence_repository, archive_service=archive_service
        ).select(NOW.date(), selected_at=NOW, archive=True)
        assert len(selected.formal_event_ids) == 1

        detail = client.get(f"/api/archive/{selected.formal_event_ids[0]}").json()
        evidence_rows = detail["versions"][0]["evidence"]
        assert {row["viewpoint"] for row in evidence_rows} == {
            "Supports adoption",
            "supports adoption!",
        }
        assert [row["coverage_percent"] for row in evidence_rows] == [100.0, 100.0]
        assert all(row["supporting_source_count"] == 2 for row in evidence_rows)
        assert all(row["valid_source_count"] == 2 for row in evidence_rows)


def test_p7_settings_validation_and_keyword_fallback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    retries: list[tuple[str, str]] = []
    delivery_retries: list[str] = []
    retry_succeeds = False

    def retry(version_id: str, stage: str) -> ProcessingOutcome:
        nonlocal retry_succeeds
        retries.append((version_id, stage))
        return ProcessingOutcome(
            version_id,
            "result-retry" if retry_succeeds else None,
            "score-retry" if retry_succeeds else None,
            80 if retry_succeeds else None,
            None if retry_succeeds else "LLM_TIMEOUT",
        )

    def retry_delivery(digest_id: str) -> DeliveryRetryResult:
        if delivery_retries:
            raise NoFailedDeliverySegmentsError(digest_id)
        delivery_retries.append(digest_id)
        return DeliveryRetryResult(digest_id, ("segment-phase7",), "SUCCESS", 1, 0)

    app = create_app(
        Settings(data_dir=tmp_path),
        retry_handler=retry,
        delivery_retry_handler=retry_delivery,
    )
    with TestClient(app) as client:
        seed(client)
        cors = client.options(
            "/api/archive",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert cors.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        fallback = client.get("/api/search", params={"q": "Agent"}).json()
        assert fallback["mode"] == "KEYWORD"
        assert fallback["degraded_reason"] == "SEMANTIC_PROVIDER_NOT_CONFIGURED"

        settings = client.get("/api/settings").json()
        settings["schedule_time"] = "09:15"
        settings["topic_order"] = list(reversed(settings["topic_order"]))
        settings.pop("updated_at")
        updated = client.put("/api/settings", json=settings)
        assert updated.status_code == 200
        assert updated.json()["topic_order"] == settings["topic_order"]

        settings["topic_order"] = ["大模型与智能体"]
        assert client.put("/api/settings", json=settings).status_code == 422

        runtime = client.app.state.runtime
        runtime.intelligence_repository.ensure_default_config(NOW)
        aggregate_id = "aggregate-phase7"
        version_id = "aggregate-version-phase7"
        run_id = "run-phase7"
        with runtime.engine.begin() as connection:
            connection.execute(
                event_aggregates.insert().values(
                    event_id=aggregate_id,
                    stable_key="7" * 64,
                    canonical_title="Retry fixture",
                    normalized_title="retry fixture",
                    current_version=1,
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
            )
            connection.execute(
                aggregate_versions.insert().values(
                    aggregate_version_id=version_id,
                    event_id=aggregate_id,
                    version_no=1,
                    change_type="NEW_EVENT",
                    change_reasons_json="[]",
                    canonical_title="Retry fixture",
                    normalized_title="retry fixture",
                    normalized_content="retry fixture",
                    content_hash="8" * 64,
                    entities_json="[]",
                    created_at=NOW.isoformat(),
                )
            )
            connection.execute(
                pipeline_runs.insert().values(
                    run_id=run_id,
                    report_date=NOW.date().isoformat(),
                    trigger_type="MANUAL",
                    window_start=NOW.isoformat(),
                    window_end=NOW.isoformat(),
                    deadline_at=NOW.isoformat(),
                    status="WAITING_RETRY",
                    owner_pid=1,
                    started_at=NOW.isoformat(),
                    heartbeat_at=NOW.isoformat(),
                    finished_at=NOW.isoformat(),
                    attempted_sources=1,
                    successful_sources=1,
                    failed_sources=0,
                    archived_count=0,
                    pending_count=1,
                    error_code="WORK_ITEMS_WAITING_RETRY",
                )
            )
            connection.execute(
                pipeline_work_items.insert().values(
                    work_item_id="work-item-phase7",
                    run_id=run_id,
                    aggregate_version_id=version_id,
                    stage="SCORING",
                    status="WAITING_RETRY",
                    updated_at=NOW.isoformat(),
                )
            )
            connection.execute(
                daily_selection_runs.insert().values(
                    selection_run_id="selection-phase7",
                    report_date=NOW.date().isoformat(),
                    config_version=1,
                    threshold=70,
                    max_items=20,
                    qualified_count=0,
                    created_at=NOW.isoformat(),
                )
            )
            connection.execute(
                daily_digests.insert().values(
                    digest_id="digest-phase7",
                    report_date=NOW.date().isoformat(),
                    version_no=1,
                    selection_run_id="selection-phase7",
                    markdown="# retained locally",
                    markdown_path="digests/2026-09-04-v0001.md",
                    content_hash="9" * 64,
                    event_ids_json="[]",
                    tier_counts_json="{}",
                    topic_order_json="[]",
                    created_at=NOW.isoformat(),
                )
            )
            connection.execute(
                delivery_segments.insert().values(
                    segment_id="segment-phase7",
                    digest_id="digest-phase7",
                    segment_no=1,
                    idempotency_key="a" * 64,
                    content="segment",
                    content_hash="b" * 64,
                    status="FAILED",
                    attempt_count=1,
                    error_code="FEISHU_SEND_FAILED",
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
            )
            connection.execute(
                telemetry_events.insert().values(
                    telemetry_event_id="telemetry-phase7",
                    event_type="daily_digest_generated",
                    run_id=run_id,
                    payload_json=json.dumps({"digest_id": "digest-phase7"}),
                    created_at=NOW.isoformat(),
                )
            )
            connection.execute(
                telemetry_events.insert().values(
                    telemetry_event_id="telemetry-source-failure-phase7",
                    event_type="source_fetch_finished",
                    run_id=run_id,
                    payload_json=json.dumps(
                        {
                            "source_id": "source-phase7",
                            "source_type": "WEB",
                            "status": "FAILED",
                            "error_stage": "FETCH",
                            "failure_reason": "upstream timeout",
                            "retry_count": 2,
                        }
                    ),
                    created_at=(NOW + timedelta(seconds=1)).isoformat(),
                )
            )
        detail = client.get(f"/api/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["retryable_work_items"][0]["stage"] == "SCORING"
        assert detail.json()["digest"]["segments"][0]["status"] == "FAILED"
        assert detail.json()["source_failures"] == [
            {
                "source_id": "source-phase7",
                "source_type": "WEB",
                "stage": "FETCH",
                "status": "FAILED",
                "reason": "upstream timeout",
                "retry_count": 2,
                "occurred_at": (NOW + timedelta(seconds=1)).isoformat(),
            }
        ]
        assert detail.json()["timeline"] == [
            {
                "event_type": "daily_digest_generated",
                "created_at": NOW.isoformat(),
                "status": None,
                "error_code": None,
            },
            {
                "event_type": "source_fetch_finished",
                "created_at": (NOW + timedelta(seconds=1)).isoformat(),
                "status": "FAILED",
                "error_code": None,
            },
        ]
        assert client.get("/api/runs/missing").status_code == 404

        redelivered = client.post("/api/digests/digest-phase7/retry-failed-segments")
        assert redelivered.status_code == 200
        assert redelivered.json()["retried_segment_ids"] == ["segment-phase7"]
        assert redelivered.json()["status"] == "SUCCESS"
        assert delivery_retries == ["digest-phase7"]
        assert client.post("/api/digests/digest-phase7/retry-failed-segments").status_code == 409
        assert client.post("/api/digests/missing/retry-failed-segments").status_code == 404

        retried = client.post(f"/api/runs/{run_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["retried"] == []
        assert retried.json()["failed"][0]["error_code"] == "LLM_TIMEOUT"
        assert retried.json()["remaining_retry_count"] == 1
        assert runtime.phase7_repository.list_retry_work_items(run_id) == [
            {"aggregate_version_id": version_id, "stage": "SCORING"}
        ]

        retry_succeeds = True
        retried = client.post(f"/api/runs/{run_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["failed"] == []
        assert retried.json()["remaining_retry_count"] == 0
        assert runtime.phase7_repository.list_retry_work_items(run_id) == []
        run_after_retry = runtime.phase6_repository.get_run(run_id)
        assert run_after_retry["status"] == "SUCCEEDED"
        assert run_after_retry["pending_count"] == 0
        assert retries == [(version_id, "SCORING"), (version_id, "SCORING")]


def test_p7_expansion_is_transient_until_favorite_and_deduplicates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=ExtensionProcessingLLM(),
    )
    with TestClient(app) as client:
        seed(client)
        before = len(client.get("/api/archive").json())
        search = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "agent safety"}
        )
        assert search.status_code == 200
        assert search.json()["status"] == "SUCCEEDED"
        assert len(client.get("/api/archive").json()) == before

        result_id = search.json()["results"][0]["result_id"]
        favorite = client.post(f"/api/extension-results/{result_id}/favorite")
        assert favorite.status_code == 200
        assert favorite.json()["deduplicated"] is False
        assert len(client.get("/api/archive").json()) == before + 1
        replayed = client.post(f"/api/extension-results/{result_id}/favorite")
        assert replayed.status_code == 200
        assert replayed.json() == favorite.json()
        assert len(client.get("/api/archive").json()) == before + 1
        archived_id = favorite.json()["event_id"]
        archived = client.get(f"/api/archive/{archived_id}").json()
        assert archived["score_id"]
        archived_version = archived["versions"][0]
        assert archived_version["score_version"] == archived["score_version"]
        assert archived_version["score_rationales"]
        assert archived_version["evidence"][0]["coverage_percent"] == 100.0
        assert set(archived["score_dimensions"]) == {
            "source_authority",
            "timeliness",
            "reach",
            "information_density",
            "innovation",
        }
        assert (
            client.post(
                "/api/feedback",
                json={
                    "score_id": archived["score_id"],
                    "reason": "extension feedback",
                    "affected_dimension": "information_density",
                    "content_features": {"origin": "EXTENDED_SEARCH"},
                },
            ).status_code
            == 200
        )
        runtime = client.app.state.runtime
        with runtime.engine.connect() as connection:
            assert connection.execute(
                formalization_links.select().where(
                    formalization_links.c.formal_event_id == archived_id
                )
            ).first()
            assert connection.execute(ai_processing_results.select()).first()

        second = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "agent safety"}
        ).json()["results"][0]["result_id"]
        deduplicated_response = client.post(f"/api/extension-results/{second}/favorite")
        deduplicated = deduplicated_response.json()
        assert deduplicated["deduplicated"] is True
        assert len(client.get("/api/archive").json()) == before + 1
        deduplicated_replay = client.post(f"/api/extension-results/{second}/favorite")
        assert deduplicated_replay.status_code == 200
        assert deduplicated_replay.json() == deduplicated
        assert len(client.get("/api/archive").json()) == before + 1


def test_ui7_extension_favorite_resumes_after_processing_timeout(tmp_path) -> None:
    llm = RetryableExtensionProcessingLLM()
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=llm,
    )
    with TestClient(app) as client:
        seed(client)
        before = len(client.get("/api/archive").json())
        result_id = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "retry processing"}
        ).json()["results"][0]["result_id"]

        failed = client.post(f"/api/extension-results/{result_id}/favorite")
        assert failed.status_code == 409
        assert failed.json()["detail"] == "extension processing failed: LLM_TIMEOUT"
        assert len(client.get("/api/archive").json()) == before

        retried = client.post(f"/api/extension-results/{result_id}/favorite")
        assert retried.status_code == 200
        assert retried.json()["deduplicated"] is False
        assert len(client.get("/api/archive").json()) == before + 1


def test_ui7_extension_favorite_serializes_same_result(tmp_path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=ExtensionProcessingLLM(),
    )
    with TestClient(app) as client:
        seed(client)
        before = len(client.get("/api/archive").json())
        result_id = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "concurrent favorite"}
        ).json()["results"][0]["result_id"]

        def favorite(_: int):  # type: ignore[no-untyped-def]
            response = client.post(f"/api/extension-results/{result_id}/favorite")
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = tuple(executor.map(favorite, (1, 2)))

        assert {status for status, _ in responses} == {200}
        assert responses[0][1] == responses[1][1]
        assert responses[0][1]["deduplicated"] is False
        assert len(client.get("/api/archive").json()) == before + 1


def test_p7_missing_expansion_configuration_is_explicit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        seed(client)
        result = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "new evidence"}
        )
        assert result.json()["status"] == "UNAVAILABLE"
        assert result.json()["error_code"] == "EXPANSION_PROVIDER_NOT_CONFIGURED"
        assert len(client.get("/api/archive").json()) == 1


def test_ui7_rejects_unsafe_extension_urls_before_render_or_favorite(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path), expansion_provider=UnsafeExpansionProvider())
    with TestClient(app) as client:
        seed(client)
        before = client.get("/api/archive").json()
        response = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "unsafe result"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "FAILED"
        assert response.json()["error_code"] == "EXPANSION_SEARCH_FAILED"
        assert response.json()["results"] == []
        assert client.get("/api/archive").json() == before


def test_ui7_manual_topic_idea_is_traceable_idempotent_and_bounded(tmp_path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=ExtensionProcessingLLM(),
    )
    with TestClient(app) as client:
        seed(client)
        search = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "product opportunity"}
        ).json()
        archived_id = client.post(
            f"/api/extension-results/{search['results'][0]['result_id']}/favorite"
        ).json()["event_id"]
        before = client.get(f"/api/archive/{archived_id}").json()
        assert before["topic_idea"] is None

        generated = client.post(f"/api/archive/{archived_id}/topic-idea")
        assert generated.status_code == 200
        assert generated.json()["created"] is True
        idea = generated.json()["idea"]
        assert idea["trigger"] == "MANUAL"
        assert set(idea) == {
            "idea_id",
            "trigger",
            "title",
            "outline",
            "hook",
            "support_evidence_ids",
            "support_sources",
            "created_at",
        }
        assert "content" not in idea
        assert "publish" not in idea

        detail = client.get(f"/api/archive/{archived_id}").json()
        assert detail["content"] == before["content"]
        support = detail["topic_idea"]["support_sources"]
        assert support == [
            {
                "evidence_id": detail["topic_idea"]["support_evidence_ids"][0],
                "source_name": "extended:external-fixture",
                "url": "https://external.example.test/new-agent",
                "viewpoint": "A relevant external result.",
            }
        ]
        repeated = client.post(f"/api/archive/{archived_id}/topic-idea")
        assert repeated.status_code == 200
        assert repeated.json()["created"] is False
        assert repeated.json()["idea"]["idea_id"] == idea["idea_id"]


def test_ui7_topic_idea_unconfigured_keeps_archive_unchanged(tmp_path) -> None:
    configured = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=ExtensionProcessingLLM(),
    )
    with TestClient(configured) as client:
        seed(client)
        search = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "manual idea"}
        ).json()
        archived_id = client.post(
            f"/api/extension-results/{search['results'][0]['result_id']}/favorite"
        ).json()["event_id"]
        original = client.get(f"/api/archive/{archived_id}").json()

    unconfigured = create_app(Settings(data_dir=tmp_path))
    with TestClient(unconfigured) as client:
        response = client.post(f"/api/archive/{archived_id}/topic-idea")
        assert response.status_code == 503
        assert response.json()["detail"] == "topic idea generation is not configured"
        after = client.get(f"/api/archive/{archived_id}").json()
        assert after["content"] == original["content"]
        assert after["topic_idea"] is None


def test_ui7_topic_idea_failure_is_retryable_and_keeps_archive_unchanged(tmp_path) -> None:
    llm = RetryableTopicIdeaLLM()
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=llm,
    )
    with TestClient(app) as client:
        seed(client)
        search = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "retryable idea"}
        ).json()
        archived_id = client.post(
            f"/api/extension-results/{search['results'][0]['result_id']}/favorite"
        ).json()["event_id"]
        original = client.get(f"/api/archive/{archived_id}").json()

        failed = client.post(f"/api/archive/{archived_id}/topic-idea")
        assert failed.status_code == 502
        assert "retry is available" in failed.json()["detail"]
        after_failure = client.get(f"/api/archive/{archived_id}").json()
        assert after_failure["content"] == original["content"]
        assert after_failure["topic_idea"] is None

        llm.fail_topic = False
        retried = client.post(f"/api/archive/{archived_id}/topic-idea")
        assert retried.status_code == 200
        assert retried.json()["created"] is True


def test_ui5_calibration_workbench_closes_confirm_rollback_and_rescore_flow(tmp_path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path),
        expansion_provider=FakeExpansionProvider(),
        processing_llm=ExtensionProcessingLLM(),
    )
    with TestClient(app) as client:
        seed(client)
        result_id = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "calibration"}
        ).json()["results"][0]["result_id"]
        archived_id = client.post(f"/api/extension-results/{result_id}/favorite").json()["event_id"]
        detail = client.get(f"/api/archive/{archived_id}").json()
        score_id = detail["score_id"]

        for index in range(4):
            response = client.post(
                "/api/feedback",
                json={
                    "score_id": score_id,
                    "reason": f"density feedback {index}",
                    "affected_dimension": "information_density",
                    "content_features": {"origin": "UI5_TEST"},
                },
            )
            assert response.status_code == 200
        insufficient = client.post("/api/calibration/proposals").json()
        assert insufficient == {"sample_count": 4, "uncertainty": "HIGH", "proposal": None}
        assert client.get("/api/calibration/workbench").json()["active_version"] == 1

        client.post(
            "/api/feedback",
            json={
                "score_id": score_id,
                "reason": "fifth density feedback",
                "affected_dimension": "information_density",
                "content_features": {},
            },
        )
        proposal = client.post("/api/calibration/proposals").json()["proposal"]
        assert proposal["base_config_version"] == 1
        duplicate = client.post("/api/calibration/proposals").json()["proposal"]
        assert duplicate["proposal_id"] == proposal["proposal_id"]
        assert len(client.get("/api/calibration/workbench").json()["proposals"]) == 1
        confirmed = client.post(
            f"/api/calibration/{proposal['proposal_id']}/confirm", json={"confirmed": True}
        )
        assert confirmed.json()["config_version"] == 2

        workbench = client.get("/api/calibration/workbench").json()
        assert workbench["active_version"] == 2
        assert [value["version"] for value in workbench["configs"]] == [2, 1]
        audit_count = len(workbench["audits"])
        no_op_rollback = client.post("/api/calibration/config/2/rollback", json={"confirmed": True})
        assert no_op_rollback.status_code == 409
        assert len(client.get("/api/calibration/workbench").json()["audits"]) == audit_count
        target = workbench["rescore_targets"][0]
        aggregate_version_id = target["aggregate_version_id"]
        score_count = target["score_count"]

        rejected = client.post(
            "/api/calibration/rescore",
            json={
                "aggregate_version_ids": [aggregate_version_id, "missing-version"],
                "confirmed": True,
            },
        )
        assert rejected.status_code == 409
        with client.app.state.runtime.engine.connect() as connection:
            assert len(connection.execute(candidate_scores.select()).all()) == score_count

        rescored = client.post(
            "/api/calibration/rescore",
            json={"aggregate_version_ids": [aggregate_version_id], "confirmed": True},
        )
        assert rescored.status_code == 200
        assert rescored.json()["appended"][0]["score_count"] == score_count + 1
        assert (
            client.get("/api/calibration/workbench").json()["rescore_targets"][0]["score_count"]
            == score_count + 1
        )

        rejected_proposal = client.post("/api/calibration/proposals").json()["proposal"]
        assert (
            client.post(f"/api/calibration/{rejected_proposal['proposal_id']}/reject").json()[
                "decision"
            ]
            == "REJECTED"
        )
        assert client.get("/api/calibration/workbench").json()["active_version"] == 2

        rollback = client.post("/api/calibration/config/1/rollback", json={"confirmed": True})
        assert rollback.status_code == 200
        final_workbench = client.get("/api/calibration/workbench").json()
        assert final_workbench["active_version"] == 1
        assert final_workbench["audits"][0]["action"] == "ROLLBACK"
        with client.app.state.runtime.engine.connect() as connection:
            event_types = set(
                connection.execute(text("SELECT event_type FROM telemetry_events")).scalars()
            )
        assert {
            "quality_feedback_submitted",
            "scoring_calibration_proposed",
            "scoring_config_changed",
        } <= event_types


def test_p7_extension_favorite_requires_processing_gate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path), expansion_provider=FakeExpansionProvider())
    with TestClient(app) as client:
        seed(client)
        search = client.post(
            f"/api/archive/{EVENT_ID}/expansion-search", json={"query": "agent safety"}
        ).json()
        result = client.post(f"/api/extension-results/{search['results'][0]['result_id']}/favorite")
        assert result.status_code == 503
        assert result.json()["detail"] == "intelligence processing is not configured"
        assert len(client.get("/api/archive").json()) == 1


def test_p7_ten_thousand_item_dashboard_and_filter_performance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runtime = initialize_runtime(Settings(data_dir=tmp_path))
    count = 10_000
    timestamp = NOW.isoformat()
    try:
        event_rows = []
        version_rows = []
        commit_rows = []
        score_rows = []
        evidence_rows = []
        metadata_rows = []
        for index in range(count):
            event_id = f"{index:08x}-0000-4000-8000-{index:012x}"
            version_id = f"v{index:035d}"
            event_rows.append(
                {
                    "event_id": event_id,
                    "canonical_title": f"Archive {index}",
                    "primary_topic": "大模型与智能体",
                    "current_version": 1,
                    "status": "READY",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            version_rows.append(
                {
                    "version_id": version_id,
                    "event_id": event_id,
                    "version_no": 1,
                    "change_type": "NEW",
                    "canonical_title": f"Archive {index}",
                    "primary_topic": "大模型与智能体",
                    "content": "content",
                    "summary": "summary",
                    "content_hash": f"{index:064x}",
                    "archive_path": f"archive/{event_id}/v0001.md",
                    "created_at": timestamp,
                }
            )
            commit_rows.append(
                {
                    "commit_id": f"c{index:035d}",
                    "event_id": event_id,
                    "version_no": 1,
                    "raw_path": f"raw/{index}.txt",
                    "raw_stage_path": f".staging/{index}/raw.tmp",
                    "raw_hash": f"{index:064x}",
                    "archive_path": f"archive/{event_id}/v0001.md",
                    "archive_stage_path": f".staging/{index}/archive.tmp",
                    "archive_hash": f"{index + 1:064x}",
                    "state": "READY",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            score_rows.append(
                {
                    "score_id": f"s{index:035d}",
                    "version_id": version_id,
                    "config_version": 1,
                    "dimensions_json": "{}",
                    "total": 80,
                    "tier": "IMPORTANT",
                    "created_at": timestamp,
                }
            )
            evidence_rows.append(
                {
                    "evidence_id": f"e{index:035d}",
                    "version_id": version_id,
                    "source_id": "performance-source",
                    "url": f"https://example.test/{index}",
                    "published_at": timestamp,
                    "published_at_original": timestamp,
                    "published_timezone": "UTC",
                    "viewpoint": "fixture",
                }
            )
            metadata_rows.append(
                {
                    "event_id": event_id,
                    "favorite": False,
                    "pinned": False,
                    "read_state": "UNREAD",
                    "trash_state": "ACTIVE",
                    "trash_reason": None,
                    "updated_at": timestamp,
                }
            )
        with runtime.engine.begin() as connection:
            connection.execute(events.insert(), event_rows)
            connection.execute(event_versions.insert(), version_rows)
            connection.execute(staged_commits.insert(), commit_rows)
            connection.execute(scores.insert(), score_rows)
            connection.execute(evidence.insert(), evidence_rows)
            connection.execute(user_metadata.insert(), metadata_rows)

        dashboard_timings = []
        for _ in range(3):
            started = perf_counter()
            dashboard = runtime.phase7_repository.dashboard(NOW.date())
            dashboard_timings.append(perf_counter() - started)
        with runtime.engine.connect() as connection:
            sqlite_count = connection.execute(text("SELECT COUNT(*) FROM events")).scalar_one()
        assert dashboard["total_count"] == sqlite_count == count
        assert len(dashboard["items"]) == 200
        assert dashboard["topic_counts"]["大模型与智能体"] == count
        assert all(elapsed <= 5 for elapsed in dashboard_timings)

        started = perf_counter()
        filtered = runtime.phase7_repository.list_archive(
            topic="大模型与智能体", tier="IMPORTANT", limit=1000
        )
        filter_elapsed = perf_counter() - started
        search_timings = []
        for _ in range(3):
            started = perf_counter()
            result = runtime.phase7_repository.search("Archive 9999", limit=20)
            search_timings.append(perf_counter() - started)
            assert result["items"]
        print(
            f"phase7-performance dashboard={dashboard_timings} "
            f"filter={filter_elapsed:.3f}s search={search_timings} items={count}"
        )
        assert len(filtered) == 1000
        assert filter_elapsed <= 2
        assert all(elapsed <= 2 for elapsed in search_timings)
    finally:
        close_runtime(runtime)


def test_ui4_settings_persist_github_rules_and_never_expose_secret_values(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/settings").json()
        assert settings["tier_caps"] == {"MUST_READ": 10, "IMPORTANT": 20, "EXTENDED": 20}
        settings["github_rules"] = {
            "daily_trending": True,
            "weekly_trending": False,
            "seven_day_star_growth": True,
            "ai_relevance": True,
            "whitelist": ["openai/openai-python", "openai/openai-python"],
        }
        settings.pop("updated_at")
        response = client.put("/api/settings", json=settings)
        assert response.status_code == 200
        assert response.json()["github_rules"]["whitelist"] == ["openai/openai-python"]

        invalid = response.json()
        invalid["github_rules"]["whitelist"] = ["invalid-repository"]
        invalid.pop("updated_at")
        assert client.put("/api/settings", json=invalid).status_code == 422

        status = client.get("/api/configuration-status").json()
        serialized = json.dumps(status, ensure_ascii=False).lower()
        assert status["semantic_search"] is False
        assert set(status["services"]) == {
            "semantic_search",
            "expansion_search",
            "intelligence_processing",
            "retry_executor",
            "feishu",
        }
        assert "key" not in serialized and "token" not in serialized and "secret" not in serialized
        scoring = client.get("/api/scoring-config").json()
        assert scoring["version"] == 1
        assert sum(scoring["weights"].values()) == 1


def test_ui4_upgrade_preserves_existing_settings(tmp_path) -> None:
    database_path = tmp_path / "existing.db"
    upgrade_database(database_path, "0009_phase7_local_web")
    engine = create_sqlite_engine(database_path)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ui_settings SET tier_caps_json = :caps, "
                    "updated_at = :updated_at WHERE singleton_id = 1"
                ),
                {
                    "caps": json.dumps({"MUST_READ": 1, "IMPORTANT": 2, "EXTENDED": 3}),
                    "updated_at": "2026-09-05T00:00:00+00:00",
                },
            )
    finally:
        engine.dispose()

    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    try:
        with engine.connect() as connection:
            caps = connection.execute(
                text("SELECT tier_caps_json FROM ui_settings WHERE singleton_id = 1")
            ).scalar_one()
            github_count = connection.execute(
                text("SELECT COUNT(*) FROM github_discovery_settings")
            ).scalar_one()
        assert json.loads(caps) == {"MUST_READ": 1, "IMPORTANT": 2, "EXTENDED": 3}
        assert github_count == 1
    finally:
        engine.dispose()
