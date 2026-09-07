from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from ai_intel.adapters.collectors import (
    GitHubCollector,
    RssCollector,
    VideoTranscriptCollector,
    WebCollector,
)
from ai_intel.adapters.manual_inbox import ManualInboxImporter
from ai_intel.api.app import create_app
from ai_intel.application.sources import CollectionService, MetricService, SourceService
from ai_intel.config import Settings
from ai_intel.domain.source import (
    CollectionFailure,
    CollectionStage,
    CollectionStatus,
    CollectionWindow,
    SourceDraft,
    SourceState,
    SourceType,
    truncate_for_model,
)
from ai_intel.domain.source_metrics import MetricStatus
from ai_intel.foundation import close_runtime, initialize_runtime
from ai_intel.infrastructure.db.migrations import MigrationSafetyError, downgrade_database
from ai_intel.infrastructure.db.source_repository import SourceRepositoryError
from tests.phase3.conftest import FixedGateway, make_source, payload

STARTED = datetime(2026, 9, 3, 9, 30, tzinfo=UTC)


class FixedGitHubGateway:
    def __init__(self) -> None:
        self.projects = {
            "org/daily": self._project("org/daily", "daily", 120, "response-daily"),
            "org/weekly": self._project("org/weekly", "weekly", 220, "response-weekly"),
            "org/whitelist": self._project("org/whitelist", "whitelist", 320, "response-whitelist"),
        }

    @staticmethod
    def _project(repository: str, suffix: str, stars: int, response_id: str) -> dict[str, object]:
        return {
            "repository": repository,
            "external_id": repository,
            "title": repository,
            "url": f"https://github.com/{repository}",
            "author": repository.split("/")[0],
            "published_at": STARTED - timedelta(days=1),
            "readme": f"README {suffix}",
            "stars": stars,
            "response_id": response_id,
            "ai_relevant": True,
        }

    def ranking(self, period: str) -> tuple[Mapping[str, object], ...]:
        if period == "daily":
            irrelevant = dict(self.projects["org/daily"], repository="org/not-ai")
            irrelevant["ai_relevant"] = False
            return self.projects["org/daily"], irrelevant
        return (self.projects["org/weekly"],)

    def project(self, repository: str) -> Mapping[str, object]:
        return self.projects[repository]


class ForbiddenMedia:
    def __init__(self) -> None:
        self.calls = 0

    def download_audio(self, url: str) -> bytes:
        self.calls += 1
        raise AssertionError(f"audio download is forbidden: {url}")


class ForbiddenSpeech:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio: bytes) -> str:
        self.calls += 1
        raise AssertionError("speech recognition is forbidden")


def test_p3_tc_03_four_collectors_follow_unified_contract(source_service) -> None:  # type: ignore[no-untyped-def]
    web = make_source(source_service, SourceType.WEB)
    rss = make_source(source_service, SourceType.RSS)
    github = make_source(source_service, SourceType.GITHUB)
    video = make_source(source_service, SourceType.VIDEO)
    window = CollectionWindow.from_started_at(STARTED)
    gateway = FixedGateway(
        {
            web.source_id: (
                payload("web-in", published_at=STARTED - timedelta(days=7)),
                payload("web-out", published_at=STARTED - timedelta(days=7, seconds=1)),
            ),
            rss.source_id: (payload("rss-in"),),
            video.source_id: (
                {
                    **payload("video-in"),
                    "description": "official metadata",
                    "official_english_transcript": "Official English transcript",
                },
            ),
        }
    )
    media, speech = ForbiddenMedia(), ForbiddenSpeech()
    batches = (
        WebCollector(gateway).collect(web, window),
        RssCollector(gateway).collect(rss, window),
        GitHubCollector(FixedGitHubGateway()).collect(github, window),
        VideoTranscriptCollector(gateway, media, speech).collect(video, window),
    )
    assert [len(batch.items) for batch in batches] == [1, 1, 2, 1]
    assert {batch.items[0].source_type for batch in batches} == {
        SourceType.WEB,
        SourceType.RSS,
        SourceType.GITHUB,
        SourceType.VIDEO,
    }


def test_p3_tc_02_fixed_window_and_missing_publication_fallback(
    source_service,
) -> None:  # type: ignore[no-untyped-def]
    source = make_source(source_service, SourceType.WEB)
    window = CollectionWindow.from_started_at(STARTED)
    assert window.window_end == STARTED
    assert window.window_start == STARTED - timedelta(days=7)
    assert window.contains(STARTED - timedelta(days=7), STARTED)
    assert not window.contains(STARTED - timedelta(days=7, seconds=1), STARTED)
    batch = WebCollector(
        FixedGateway({source.source_id: (payload("unknown-date", published_at=None),)})
    ).collect(source, window)
    item = batch.items[0]
    assert item.published_at == STARTED
    assert item.first_seen_at == STARTED
    assert item.published_at_unknown is True


def test_p3_tc_04_video_without_official_transcript_is_metadata_only(
    source_service,
) -> None:  # type: ignore[no-untyped-def]
    source = make_source(source_service, SourceType.VIDEO)
    media, speech = ForbiddenMedia(), ForbiddenSpeech()
    fixture = {
        **payload("video-no-transcript"),
        "description": "Public title and description only",
        "official_english_transcript": None,
    }
    batch = VideoTranscriptCollector(
        FixedGateway({source.source_id: (fixture,)}), media, speech
    ).collect(source, CollectionWindow.from_started_at(STARTED))
    assert batch.items[0].status is CollectionStatus.METADATA_ONLY
    assert batch.items[0].metadata["official_english_transcript"] is False
    assert media.calls == speech.calls == 0


def test_p3_tc_05_github_rules_and_local_seven_day_metric(runtime, source_service) -> None:  # type: ignore[no-untyped-def]
    source = make_source(source_service, SourceType.GITHUB)
    collector = GitHubCollector(FixedGitHubGateway(), ("org/whitelist",))
    batch = collector.collect(source, CollectionWindow.from_started_at(STARTED))
    by_repository = {str(item.metadata["repository"]): item for item in batch.items}
    assert set(by_repository) == {"org/daily", "org/weekly", "org/whitelist"}
    assert by_repository["org/daily"].metadata["discovery_rules"] == [
        "ai_relevance",
        "daily_trending",
    ]
    assert by_repository["org/weekly"].metadata["discovery_rules"] == [
        "ai_relevance",
        "weekly_trending",
    ]
    assert by_repository["org/whitelist"].metadata["discovery_rules"] == ["whitelist"]

    class RankingFailureGateway(FixedGitHubGateway):
        def ranking(self, period: str) -> tuple[Mapping[str, object], ...]:
            raise RuntimeError(f"{period} fixed ranking failure")

    isolated = GitHubCollector(RankingFailureGateway(), ("org/whitelist",)).collect(
        source, CollectionWindow.from_started_at(STARTED)
    )
    assert [item.metadata["repository"] for item in isolated.items] == ["org/whitelist"]
    assert len(isolated.failures) == 2

    metrics = MetricService(runtime.source_repository)
    first = metrics.record_and_calculate(
        source_id=source.source_id,
        subject_key="org/daily",
        metric_type="stars",
        observed_at=STARTED - timedelta(days=8),
        value=100,
        response_id="response-older",
    )
    second = metrics.record_and_calculate(
        source_id=source.source_id,
        subject_key="org/daily",
        metric_type="stars",
        observed_at=STARTED,
        value=120,
        response_id="response-current",
    )
    assert first.status is MetricStatus.INSUFFICIENT_HISTORY
    assert second.status is MetricStatus.OK
    assert second.growth == 20
    assert second.actual_interval_seconds == 8 * 24 * 60 * 60
    with pytest.raises(DatabaseError, match="append-only"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE source_metric_snapshots SET value=999"))


def test_p3_tc_06_truncation_changes_next_run_only_and_preserves_raw(
    runtime, source_service
) -> None:  # type: ignore[no-untyped-def]
    source = make_source(source_service, SourceType.WEB)
    content = "x" * 55_000
    fixtures: dict[str, tuple[Mapping[str, object], ...]] = {
        source.source_id: (payload("before-change", content=content),)
    }
    service = CollectionService(
        runtime.source_repository, {SourceType.WEB: WebCollector(FixedGateway(fixtures))}
    )
    first_plan = service.plan(STARTED)
    source_service.update(
        source.source_id,
        SourceDraft(
            "web",
            SourceType.WEB,
            source.url,
            source.topic,
            source.authority_level,
            10_000,
        ),
    )
    service.execute(first_plan)
    fixtures[source.source_id] = (payload("after-change", content=content),)
    service.run(STARTED + timedelta(minutes=1))
    rows = runtime.source_repository.list_collected()
    assert [len(str(row["model_input"])) for row in rows] == [20_000, 10_000]
    assert all(
        (runtime.data_dir / str(row["raw_path"])).read_text(encoding="utf-8") == content
        for row in rows
    )
    expected_hash = sha256(content.encode()).hexdigest()
    assert all(str(row["content_hash"]) == expected_hash for row in rows)
    with pytest.raises(DatabaseError, match="append-only"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE collected_raw_snapshots SET title='tampered'"))
    cases = (
        ("x" * 9_999, 20_000, 9_999),
        ("x" * 10_001, 10_000, 10_000),
        ("x" * 20_001, 20_000, 20_000),
        ("x" * 50_001, 50_000, 50_000),
    )
    assert [len(truncate_for_model(raw, limit)) for raw, limit, _ in cases] == [
        expected for _, _, expected in cases
    ]


def test_p3_tc_01_source_and_expert_lifecycle_takes_effect_next_run(
    runtime, source_service
) -> None:  # type: ignore[no-untyped-def]
    source = make_source(source_service, SourceType.RSS)
    expert = source_service.create_expert("Expert A", (source.source_id,))
    assert expert.source_ids == (source.source_id,)
    planned_before_pause = runtime.source_repository.plan_run(STARTED)
    source_service.pause(source.source_id)
    assert planned_before_pause.sources[0].state is SourceState.ACTIVE
    assert runtime.source_repository.plan_run(STARTED).automatic_source_count == 0
    source_service.resume(source.source_id)
    resumed = runtime.source_repository.plan_run(STARTED + timedelta(days=20))
    assert resumed.window.window_start == STARTED + timedelta(days=13)
    assert resumed.automatic_source_count == 1
    paused_expert = source_service.set_expert_state(expert.expert_id, SourceState.PAUSED)
    active_expert = source_service.set_expert_state(expert.expert_id, SourceState.ACTIVE)
    assert paused_expert.state is SourceState.PAUSED
    assert active_expert.state is SourceState.ACTIVE
    updated_expert = source_service.update_expert(
        expert.expert_id, "Expert A updated", (source.source_id,)
    )
    assert updated_expert.name == "Expert A updated"
    collection = CollectionService(
        runtime.source_repository,
        {
            SourceType.RSS: RssCollector(
                FixedGateway(
                    {
                        source.source_id: (
                            payload(
                                "retained-history",
                                published_at=resumed.window.window_end - timedelta(days=1),
                            ),
                        )
                    }
                )
            )
        },
    )
    collection.execute(resumed)
    source_service.set_expert_state(expert.expert_id, SourceState.DELETED)
    assert source_service.list_experts() == ()
    assert source_service.list_experts(include_deleted=True)[0].state is SourceState.DELETED
    source_service.delete(source.source_id)
    assert source_service.list() == ()
    assert source_service.list(include_deleted=True)[0].state is SourceState.DELETED
    assert runtime.source_repository.list_collected()[0]["source_id"] == source.source_id
    with pytest.raises(SourceRepositoryError):
        source_service.resume(source.source_id)


def test_p3_tc_07_one_source_failure_does_not_block_other_sources(runtime, source_service) -> None:  # type: ignore[no-untyped-def]
    failed = make_source(source_service, SourceType.WEB, name="failed")
    extraction_failed = make_source(source_service, SourceType.WEB, name="extraction-failed")
    make_source(source_service, SourceType.RSS, name="healthy")

    class IsolatedGateway:
        def load(self, source):  # type: ignore[no-untyped-def]
            if source.source_id == failed.source_id:
                raise RuntimeError("fixed upstream failure")
            if source.source_id == extraction_failed.source_id:
                value = payload("metadata-only")
                del value["content"]
                return (value,)
            return (payload("healthy-item"),)

    gateway = IsolatedGateway()
    service = CollectionService(
        runtime.source_repository,
        {SourceType.WEB: WebCollector(gateway), SourceType.RSS: RssCollector(gateway)},
    )
    result = service.run(STARTED)
    assert len(result.saved_snapshot_ids) == 2
    assert len(result.failures) == 2
    assert {failure.reason for failure in result.failures} == {
        "fixed upstream failure",
        "fixture field content must be a string",
    }
    assert {row["status"] for row in runtime.source_repository.list_collected()} == {
        "COLLECTED",
        "METADATA_ONLY",
    }
    assert len(runtime.source_repository.list_failures(result.plan.run_id)) == 2


def test_collectors_preserve_valid_items_when_one_payload_is_malformed(
    source_service,
) -> None:  # type: ignore[no-untyped-def]
    web = make_source(source_service, SourceType.WEB)
    video = make_source(source_service, SourceType.VIDEO)
    valid_web = payload("valid-web")
    malformed_web = payload("malformed-web")
    malformed_web["url"] = "not-an-absolute-url"
    web_batch = WebCollector(FixedGateway({web.source_id: (valid_web, malformed_web)})).collect(
        web, CollectionWindow.from_started_at(STARTED)
    )

    valid_video = {
        **payload("valid-video"),
        "description": "Valid description",
        "official_english_transcript": "Valid official transcript",
    }
    malformed_video = {
        **payload("malformed-video"),
        "url": "not-an-absolute-url",
        "description": "Malformed description",
        "official_english_transcript": "Malformed transcript",
    }
    media, speech = ForbiddenMedia(), ForbiddenSpeech()
    video_batch = VideoTranscriptCollector(
        FixedGateway({video.source_id: (valid_video, malformed_video)}), media, speech
    ).collect(video, CollectionWindow.from_started_at(STARTED))

    for batch in (web_batch, video_batch):
        assert len(batch.items) == 1
        assert len(batch.failures) == 1
        assert batch.failures[0].stage is CollectionStage.EXTRACT
    assert media.calls == speech.calls == 0


def test_p3_tc_08_manual_inbox_valid_duplicate_and_corrupt_are_traceable(
    runtime, source_service
) -> None:  # type: ignore[no-untyped-def]
    make_source(source_service, SourceType.WEB)
    automatic_before = runtime.source_repository.plan_run(STARTED).automatic_source_count
    valid = runtime.data_dir / "manual-inbox" / "valid.md"
    valid.write_text(
        "---\ntitle: Manual intelligence\nsource_url: https://manual.example.test/item\n"
        "author: Analyst\n---\nOriginal manual body.\n",
        encoding="utf-8",
    )
    corrupt = runtime.data_dir / "manual-inbox" / "corrupt.md"
    corrupt.write_text("not front matter", encoding="utf-8")
    importer = ManualInboxImporter(runtime.data_dir, runtime.source_repository)
    first = importer.import_file(valid, imported_at=STARTED)
    duplicate = importer.import_file(valid, imported_at=STARTED + timedelta(minutes=1))
    failed = importer.import_file(corrupt, imported_at=STARTED)
    retry = importer.import_file(corrupt, imported_at=STARTED + timedelta(minutes=1))
    assert first.status is CollectionStatus.COLLECTED
    assert duplicate.status is CollectionStatus.DUPLICATE
    assert failed.status is retry.status is CollectionStatus.FAILED
    assert retry.failure is not None and retry.failure.retry_count == 1
    assert runtime.source_repository.get_manual_import(first.file_hash)["snapshot_id"] == (
        first.snapshot_id
    )
    assert runtime.source_repository.plan_run(STARTED).automatic_source_count == automatic_before


def test_source_api_contract_supports_crud_pause_resume_and_logical_delete(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    body = {
        "name": "Official blog",
        "source_type": "WEB",
        "url": "https://official.example.test/blog",
        "topic": "AI",
        "authority_level": 5,
        "truncate_chars": 20000,
    }
    with TestClient(app) as client:
        created = client.post("/api/sources", json=body)
        source_id = created.json()["source_id"]
        assert created.status_code == 200
        assert (
            client.post(f"/api/sources/{source_id}/state", json={"state": "PAUSED"}).json()["state"]
            == "PAUSED"
        )
        assert (
            client.post(f"/api/sources/{source_id}/state", json={"state": "ACTIVE"}).json()["state"]
            == "ACTIVE"
        )
        body["truncate_chars"] = 10000
        assert client.put(f"/api/sources/{source_id}", json=body).json()["truncate_chars"] == 10000
        invalid_body = dict(body)
        invalid_body["url"] = "not-an-absolute-url"
        invalid_update = client.put(f"/api/sources/{source_id}", json=invalid_body)
        assert invalid_update.status_code == 422
        assert client.get("/api/sources").json()[0]["url"] == body["url"]
        expert = client.post("/api/experts", json={"name": "Expert API", "source_ids": [source_id]})
        expert_id = expert.json()["expert_id"]
        assert expert.status_code == 200
        assert len(client.get("/api/experts").json()) == 1
        runtime = client.app.state.runtime
        collection = CollectionService(
            runtime.source_repository,
            {SourceType.WEB: WebCollector(FixedGateway({source_id: (payload("api-operation"),)}))},
        )
        collection.run(STARTED)
        runtime.source_repository.save_failure(
            None,
            CollectionFailure(
                source_id,
                CollectionStage.FETCH,
                "redacted-safe fixture failure",
                STARTED,
                retry_count=1,
            ),
        )
        operation = client.get("/api/source-operations").json()[0]
        assert operation["source_id"] == source_id
        assert operation["latest_collection"]["status"] == "COLLECTED"
        assert operation["latest_failure"]["stage"] == "FETCH"
        assert operation["latest_failure"]["retry_count"] == 1
        assert client.delete(f"/api/experts/{expert_id}").json()["state"] == "DELETED"
        assert client.delete(f"/api/sources/{source_id}").json()["state"] == "DELETED"
        assert client.get("/api/sources").json() == []
        assert len(client.get("/api/sources?include_deleted=true").json()) == 1


def test_phase3_populated_database_refuses_destructive_downgrade(runtime, source_service) -> None:  # type: ignore[no-untyped-def]
    make_source(source_service, SourceType.WEB)
    with pytest.raises(MigrationSafetyError, match="source_configs"):
        downgrade_database(runtime.database_path)


def test_phase3_raw_snapshot_survives_application_restart(tmp_path: Path) -> None:
    first_runtime = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        service = SourceService(first_runtime.source_repository)
        source = make_source(service, SourceType.WEB)
        collection = CollectionService(
            first_runtime.source_repository,
            {
                SourceType.WEB: WebCollector(
                    FixedGateway({source.source_id: (payload("restart-safe"),)})
                )
            },
        )
        result = collection.run(STARTED)
        assert len(result.saved_snapshot_ids) == 1
        row = first_runtime.source_repository.list_collected()[0]
        raw_path = tmp_path / str(row["raw_path"])
        assert raw_path.exists()
    finally:
        close_runtime(first_runtime)

    second_runtime = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        assert raw_path.exists()
        assert second_runtime.source_repository.list_collected()[0]["raw_path"] == row["raw_path"]
        assert list((tmp_path / "quarantine" / "orphan").glob("*")) == []
    finally:
        close_runtime(second_runtime)
