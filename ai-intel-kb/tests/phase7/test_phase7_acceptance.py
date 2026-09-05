import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import text

from ai_intel.api.app import create_app
from ai_intel.application.archive import ArchiveService
from ai_intel.application.search import ExternalSearchHit, SearchDocument
from ai_intel.config import Settings
from ai_intel.domain.models import ArchiveCandidate, EvidenceInput, ScoreInput
from ai_intel.domain.states import Tier
from ai_intel.foundation import close_runtime, initialize_runtime
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter
from ai_intel.infrastructure.db.schema import (
    aggregate_versions,
    ai_processing_results,
    event_aggregates,
    event_versions,
    events,
    evidence,
    formalization_links,
    pipeline_runs,
    pipeline_work_items,
    scores,
    staged_commits,
    user_metadata,
)
from ai_intel.infrastructure.vault_projection.projector import VaultProjector
from ai_intel.ports.llm import LLMRequest

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


class ExtensionProcessingLLM:
    def complete(self, request: LLMRequest) -> str:
        evidence_id = str(request.context["evidence_ids"][0])
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


def seed(client: TestClient) -> None:
    runtime = client.app.state.runtime
    ArchiveService(
        runtime.repository,
        AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
        VaultProjector(runtime.data_dir, runtime.repository),
    ).commit(candidate())


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
        assert len(detail.json()["versions"][0]["evidence"]) == 2
        assert "<script>" in detail.json()["content"]
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


def test_p7_settings_validation_and_keyword_fallback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    retries: list[tuple[str, str]] = []
    app = create_app(
        Settings(data_dir=tmp_path),
        retry_handler=lambda version_id, stage: retries.append((version_id, stage)),
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
        retried = client.post(f"/api/runs/{run_id}/retry")
        assert retried.status_code == 200
        assert retries == [(version_id, "SCORING")]


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
        archived_id = favorite.json()["event_id"]
        archived = client.get(f"/api/archive/{archived_id}").json()
        assert archived["score_id"]
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
        deduplicated = client.post(f"/api/extension-results/{second}/favorite").json()
        assert deduplicated["deduplicated"] is True
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
