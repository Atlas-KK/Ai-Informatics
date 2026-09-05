import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest

from ai_intel.adapters.feishu import FakeFeishuSender
from ai_intel.adapters.llm import FakeLLM
from ai_intel.application.archive import ArchiveService
from ai_intel.application.calibration import CalibrationService
from ai_intel.application.daily_selection import DailySelectionService
from ai_intel.application.delivery import DeliveryService
from ai_intel.application.digest import DigestService
from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.application.intelligence_processing import IntelligenceProcessingService
from ai_intel.application.pipeline import PipelineService
from ai_intel.application.sources import CollectionService, SourceService
from ai_intel.config import MissingConfigurationError, Settings
from ai_intel.domain.pipeline import PipelineRunStatus, PipelineTrigger
from ai_intel.domain.source import (
    CollectedItem,
    CollectionBatch,
    CollectionStatus,
    SourceConfig,
    SourceDraft,
    SourceType,
)
from ai_intel.foundation import close_runtime, initialize_runtime
from ai_intel.infrastructure.archive.commit import AtomicArchiveCommitter
from ai_intel.infrastructure.db.schema import pipeline_work_items
from ai_intel.infrastructure.scheduler import PipelineCoordinator
from ai_intel.infrastructure.telemetry import TelemetryEventType, TelemetryRecorder
from ai_intel.infrastructure.vault_projection.projector import VaultProjector
from ai_intel.ports.llm import LLMRequest
from tests.phase5.conftest import (
    REPORT_DATE,
    add_candidate,
    aggregate_version_for_snapshot,
    processing_response,
)

NOW = datetime(2026, 9, 4, 1, tzinfo=UTC)


class FakeClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class DynamicLLM:
    def __init__(self, clock: FakeClock | None = None, advance_after_first: bool = False) -> None:
        self.clock = clock
        self.advance_after_first = advance_after_first
        self.calls = 0

    def complete(self, request: LLMRequest) -> str:
        self.calls += 1
        evidence_id = str(request.context["evidence_ids"][0])
        response = processing_response(evidence_id, density=100, innovation=100)
        if self.advance_after_first and self.calls == 1:
            assert self.clock is not None
            self.clock.advance(timedelta(hours=2, seconds=1))
        return response


class TopicLLM:
    def __init__(self, topics_by_title: dict[str, str]) -> None:
        self.topics_by_title = topics_by_title

    def complete(self, request: LLMRequest) -> str:
        evidence_id = str(request.context["evidence_ids"][0])
        return processing_response(
            evidence_id,
            topic=self.topics_by_title[str(request.context["title"])],
            density=100,
            innovation=100,
        )


class SelectiveCollector:
    def __init__(self, failing_source_id: str | None = None, secret_error: bool = False) -> None:
        self.failing_source_id = failing_source_id
        self.secret_error = secret_error

    def collect(self, source: SourceConfig, window) -> CollectionBatch:  # type: ignore[no-untyped-def]
        if source.source_id == self.failing_source_id:
            if self.secret_error:
                raise RuntimeError(
                    "Authorization: Bearer super-secret Token=abc123 Cookie=session456"
                )
            raise RuntimeError("fixture source failure")
        item = CollectedItem(
            external_id=source.source_id,
            source_id=source.source_id,
            source_type=source.source_type,
            title=f"Unique release {source.name}",
            url=f"https://content.example.test/{source.source_id}",
            author="Fixture",
            published_at=window.window_end,
            first_seen_at=window.window_end,
            published_at_unknown=False,
            raw_content=f"A distinct AI agent capability from {source.name}.",
            model_input=f"A distinct AI agent capability from {source.name}.",
            status=CollectionStatus.COLLECTED,
            metadata={"viewpoint": "A verified product capability", "entities": [source.name]},
        )
        return CollectionBatch((item,))


class TimeoutFeishuSender:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def send_private(self, segment) -> None:  # type: ignore[no-untyped-def]
        self.attempts.append(segment.idempotency_key)
        raise TimeoutError("fixture network timeout")


@pytest.fixture
def runtime(tmp_path):  # type: ignore[no-untyped-def]
    context = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        yield context
    finally:
        close_runtime(context)


def create_source(runtime, name: str) -> SourceConfig:  # type: ignore[no-untyped-def]
    return SourceService(runtime.source_repository).create(
        SourceDraft(
            name=name,
            source_type=SourceType.WEB,
            url=f"https://{name.lower()}.example.test/feed",
            topic="AI product intelligence",
            authority_level=5,
        )
    )


def build_pipeline(  # type: ignore[no-untyped-def]
    runtime, clock, collectors, llm, sender=None, topic_order=None
):
    telemetry = TelemetryRecorder(runtime.engine)
    archive = ArchiveService(
        runtime.repository,
        AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
        VaultProjector(runtime.data_dir, runtime.repository),
        telemetry,
    )
    selection = DailySelectionService(runtime.intelligence_repository, archive_service=archive)
    digest = DigestService(
        runtime.phase6_repository,
        runtime.intelligence_repository,
        archive,
        telemetry,
        **({} if topic_order is None else {"topic_order": topic_order}),
    )
    delivery = (
        None
        if sender is None
        else DeliveryService(runtime.phase6_repository, telemetry, sender, max_segment_chars=300)
    )
    coordinator = PipelineCoordinator(runtime.phase6_repository, clock)
    return (
        PipelineService(
            repository=runtime.phase6_repository,
            coordinator=coordinator,
            telemetry=telemetry,
            collection=CollectionService(runtime.source_repository, collectors),
            aggregation=EventAggregationService(runtime.event_repository),
            processing=IntelligenceProcessingService(runtime.intelligence_repository, llm),
            selection=selection,
            digest=digest,
            clock=clock,
            delivery=delivery,
        ),
        telemetry,
        archive,
    )


def test_p6_tc_01_unique_lock_stale_recovery_and_latest_catch_up(runtime) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock()
    coordinator = PipelineCoordinator(runtime.phase6_repository, clock)
    barrier = Barrier(2)

    def start_concurrently(owner_pid: int):  # type: ignore[no-untyped-def]
        barrier.wait()
        return coordinator.start(date(2026, 9, 2), PipelineTrigger.SCHEDULED, owner_pid=owner_pid)

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = tuple(executor.map(start_concurrently, (101, 202)))

    assert sum(acquired for _, acquired in attempts) == 1
    first = next(run for run, acquired in attempts if acquired)
    duplicate = next(run for run, acquired in attempts if not acquired)
    assert duplicate.status is PipelineRunStatus.REJECTED_DUPLICATE
    assert first.window.window_end - first.window.window_start == timedelta(days=7)

    clock.advance(timedelta(minutes=6))
    assert coordinator.recover_stale(lambda _pid: False) == first.run_id
    assert runtime.phase6_repository.get_run(first.run_id)["status"] == "WAITING_RETRY"
    assert coordinator.latest_catch_up_date() == date(2026, 9, 2)
    missed = (
        NOW - timedelta(days=3),
        NOW - timedelta(days=2),
        NOW - timedelta(days=1),
    )
    assert coordinator.latest_missed_schedule(missed) == missed[-1]


def test_p6_tc_02_deadline_stops_new_work_and_marks_remainder(runtime) -> None:  # type: ignore[no-untyped-def]
    for suffix, title in (("deadline-a", "Quantum compiler"), ("deadline-b", "Medical robot")):
        add_candidate(runtime, suffix, title=title, content=f"A distinct release for {title}.")
    clock = FakeClock()
    pipeline, _, _ = build_pipeline(
        runtime,
        clock,
        {},
        DynamicLLM(clock, advance_after_first=True),
    )

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)

    assert result.status is PipelineRunStatus.TIMED_OUT
    assert result.pending_count == 1
    assert result.archived_count == 1
    assert result.digest_id is not None
    rows = runtime.intelligence_repository.table_rows(pipeline_work_items)
    assert sorted(row["status"] for row in rows) == ["COMPLETED", "WAITING_RETRY"]
    assert runtime.phase6_repository.get_run(result.run_id)["error_code"] == (
        "PIPELINE_DEADLINE_EXCEEDED"
    )


def test_p6_tc_02_single_item_crossing_deadline_never_reports_success(runtime) -> None:  # type: ignore[no-untyped-def]
    add_candidate(
        runtime,
        "single-deadline",
        title="Single long-running candidate",
        content="One candidate crosses the deadline while processing.",
    )
    clock = FakeClock()
    pipeline, _, _ = build_pipeline(
        runtime,
        clock,
        {},
        DynamicLLM(clock, advance_after_first=True),
    )

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)

    assert result.status is PipelineRunStatus.TIMED_OUT
    assert result.pending_count == 0
    assert result.archived_count == 1
    assert result.digest_id is not None


def test_p6_tc_03_empty_digest_is_versioned_local_markdown(runtime) -> None:  # type: ignore[no-untyped-def]
    telemetry = TelemetryRecorder(runtime.engine)
    archive = ArchiveService(
        runtime.repository,
        AtomicArchiveCommitter(runtime.data_dir, runtime.repository),
        VaultProjector(runtime.data_dir, runtime.repository),
    )
    selection = DailySelectionService(
        runtime.intelligence_repository, archive_service=archive
    ).select(REPORT_DATE, selected_at=NOW, archive=True)
    service = DigestService(
        runtime.phase6_repository,
        runtime.intelligence_repository,
        archive,
        telemetry,
    )

    digest = service.generate(REPORT_DATE, selection, generated_at=NOW)

    assert digest.event_ids == ()
    assert "今日无达标情报" in digest.markdown
    assert (runtime.data_dir / digest.markdown_path).read_text(encoding="utf-8") == digest.markdown
    assert telemetry.list()[0]["event_type"] == "daily_digest_generated"


def test_p6_tc_03_nonempty_digest_and_push_honor_configured_topic_order(runtime) -> None:  # type: ignore[no-untyped-def]
    topics_by_title = {
        "Agent release alpha": "大模型与智能体",
        "Agent release beta": "大模型与智能体",
        "Product practice alpha": "AI 产品实战",
        "Product practice beta": "AI 产品实战",
    }
    for index, title in enumerate(topics_by_title):
        add_candidate(
            runtime,
            f"topic-order-{index}",
            title=title,
            content=f"Distinct capability for {title}.",
        )
    topic_order = ("AI 产品实战", "大模型与智能体")
    sender = FakeFeishuSender()
    pipeline, _, archive = build_pipeline(
        runtime,
        FakeClock(),
        {},
        TopicLLM(topics_by_title),
        sender,
        topic_order,
    )

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)

    assert result.status is PipelineRunStatus.SUCCEEDED
    assert result.digest_id is not None
    digest = runtime.phase6_repository.get_digest(result.digest_id)
    assert digest.topic_order == topic_order
    assert digest.markdown.index("## 必读 · AI 产品实战") < digest.markdown.index(
        "## 必读 · 大模型与智能体"
    )
    assert set(digest.event_ids) == {record.event_id for record in archive.list_formal_archive()}
    persisted_segments = runtime.phase6_repository.list_segments(digest.digest_id)
    assert [segment.segment_no for segment in sender.sent_segments] == list(
        range(1, len(persisted_segments) + 1)
    )
    assert {segment.idempotency_key for segment in sender.sent_segments} == {
        segment.idempotency_key for segment in persisted_segments
    }


def test_p6_tc_04_partial_and_total_delivery_failures_retry_failed_only(runtime) -> None:  # type: ignore[no-untyped-def]
    selection = DailySelectionService(runtime.intelligence_repository).select(
        REPORT_DATE, selected_at=NOW
    )
    markdown = "\n".join(f"segment line {index} " + "x" * 80 for index in range(8))
    digest = runtime.phase6_repository.save_digest(
        report_date=REPORT_DATE,
        selection_run_id=selection.selection_run_id,
        markdown=markdown,
        event_ids=(),
        tier_counts={"MUST_READ": 0, "IMPORTANT": 0, "EXTENDED": 0},
        topic_order=(),
        created_at=NOW,
    )
    sender = FakeFeishuSender({2})
    service = DeliveryService(
        runtime.phase6_repository,
        TelemetryRecorder(runtime.engine),
        sender,
        max_segment_chars=200,
    )
    first = service.push(digest.digest_id, pushed_at=NOW)
    successful_keys = set(sender.sent)
    assert first.status == "PARTIAL"

    sender.fail_segment_numbers.clear()
    second = service.push(digest.digest_id, pushed_at=NOW + timedelta(minutes=1))
    assert second.status == "SUCCESS"
    assert all(sender.attempts.count(key) == 1 for key in successful_keys)

    second_digest = runtime.phase6_repository.save_digest(
        report_date=REPORT_DATE,
        selection_run_id=selection.selection_run_id,
        markdown=markdown,
        event_ids=(),
        tier_counts={"MUST_READ": 0, "IMPORTANT": 0, "EXTENDED": 0},
        topic_order=(),
        created_at=NOW,
    )
    all_fail = FakeFeishuSender(set(range(1, 20)))
    failed = DeliveryService(
        runtime.phase6_repository,
        TelemetryRecorder(runtime.engine),
        all_fail,
        max_segment_chars=200,
    ).push(second_digest.digest_id, pushed_at=NOW)
    assert failed.status == "FAILED"
    assert runtime.phase6_repository.get_digest(second_digest.digest_id).markdown == markdown

    timeout_digest = runtime.phase6_repository.save_digest(
        report_date=REPORT_DATE,
        selection_run_id=selection.selection_run_id,
        markdown=markdown,
        event_ids=(),
        tier_counts={"MUST_READ": 0, "IMPORTANT": 0, "EXTENDED": 0},
        topic_order=(),
        created_at=NOW,
    )
    timeout_sender = TimeoutFeishuSender()
    timeout_result = DeliveryService(
        runtime.phase6_repository,
        TelemetryRecorder(runtime.engine),
        timeout_sender,
        max_segment_chars=200,
    ).push(timeout_digest.digest_id, pushed_at=NOW)
    timeout_segments = runtime.phase6_repository.list_segments(timeout_digest.digest_id)
    assert timeout_result.status == "FAILED"
    assert len(timeout_sender.attempts) == len(timeout_segments)
    assert all(segment.status.value == "FAILED" for segment in timeout_segments)
    assert all(segment.attempt_count == 1 for segment in timeout_segments)


def test_p6_tc_05_retry_reuses_collection_and_aggregation(runtime) -> None:  # type: ignore[no-untyped-def]
    snapshot = add_candidate(
        runtime,
        "retry-processing",
        title="Retry processing stage",
        content="A reusable collected source needs model retry.",
    )
    version_id = aggregate_version_for_snapshot(runtime, snapshot)
    context = runtime.intelligence_repository.get_candidate_context(version_id)
    llm = FakeLLM(["bad-json", processing_response(context.evidence[0].evidence_id)])
    pipeline, _, _ = build_pipeline(runtime, FakeClock(), {}, llm)
    before = len(runtime.source_repository.list_collected())

    failed = pipeline.retry_candidate(version_id, retried_at=NOW)
    succeeded = pipeline.retry_candidate(version_id, retried_at=NOW + timedelta(minutes=1))

    assert failed.failure_code == "INVALID_MODEL_OUTPUT"
    assert succeeded.succeeded
    assert len(runtime.source_repository.list_collected()) == before


def test_p6_tc_05_processing_failure_keeps_run_eligible_for_catch_up(runtime) -> None:  # type: ignore[no-untyped-def]
    snapshot = add_candidate(
        runtime,
        "pipeline-processing-failure",
        title="Pipeline processing failure",
        content="A model failure must remain visible to catch-up orchestration.",
    )
    aggregate_version_id = aggregate_version_for_snapshot(runtime, snapshot)
    pipeline, _, archive = build_pipeline(runtime, FakeClock(), {}, FakeLLM(["bad-json"]))

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)

    assert result.status is PipelineRunStatus.WAITING_RETRY
    assert result.pending_count == 1
    assert result.digest_id is not None
    assert runtime.phase6_repository.latest_incomplete_run() is not None
    assert pipeline.coordinator.latest_catch_up_date() == REPORT_DATE
    assert runtime.intelligence_repository.existing_formalization(aggregate_version_id) is None
    assert archive.list_formal_archive() == []
    rows = runtime.intelligence_repository.table_rows(pipeline_work_items)
    assert [(row["stage"], row["status"]) for row in rows] == [("PROCESSING", "WAITING_RETRY")]

    collected_before_retry = len(runtime.source_repository.list_collected())
    retry_pipeline, _, _ = build_pipeline(
        runtime,
        FakeClock(NOW + timedelta(minutes=1)),
        {},
        DynamicLLM(),
    )
    retried = retry_pipeline.run(REPORT_DATE, trigger=PipelineTrigger.CATCH_UP)
    assert retried.status is PipelineRunStatus.SUCCEEDED
    assert len(archive.list_formal_archive()) == 1
    assert len(runtime.source_repository.list_collected()) == collected_before_retry
    assert retry_pipeline.coordinator.latest_catch_up_date() is None


def test_p6_tc_06_all_twelve_telemetry_contracts_are_local_and_complete(runtime) -> None:  # type: ignore[no-untyped-def]
    recorder = TelemetryRecorder(runtime.engine)
    payloads = {
        TelemetryEventType.PIPELINE_RUN_STARTED: {
            "run_id": "r",
            "trigger_type": "MANUAL",
            "window_start": "s",
            "window_end": "e",
            "started_at": "t",
            "enabled_source_ids": ["s"],
        },
        TelemetryEventType.PIPELINE_RUN_FINISHED: {
            "run_id": "r",
            "status": "SUCCEEDED",
            "duration": 1,
            "attempted_sources": 1,
            "successful_sources": 1,
            "failed_sources": 0,
            "archived_count": 1,
        },
        TelemetryEventType.SOURCE_FETCH_FINISHED: {
            "run_id": "r",
            "source_id": "s",
            "source_type": "WEB",
            "status": "SUCCESS",
            "item_count": 1,
            "error_stage": None,
        },
        TelemetryEventType.INTEL_CHANGE_DETECTED: {
            "item_id": "i",
            "event_id": "e",
            "change_type": "NEW",
            "source_id": "s",
            "detected_at": "t",
        },
        TelemetryEventType.INTEL_ITEM_SCORED: {
            "item_id": "i",
            "total_score": 90,
            "dimension_scores": {},
            "scoring_version": 1,
            "topic": "topic",
            "tier": "MUST_READ",
        },
        TelemetryEventType.DAILY_DIGEST_GENERATED: {
            "digest_id": "d",
            "date": "d",
            "qualified_count": 1,
            "archived_count": 1,
            "must_read_count": 1,
            "important_count": 0,
            "extended_count": 0,
        },
        TelemetryEventType.DAILY_DIGEST_PUSHED: {
            "date": "d",
            "status": "SUCCESS",
            "successful_segments": 1,
            "failed_segments": 0,
            "error_code": None,
        },
        TelemetryEventType.QUALITY_FEEDBACK_SUBMITTED: {
            "item_id": "i",
            "original_score": 1,
            "reason": "r",
            "scoring_version": 1,
            "occurred_at": "t",
        },
        TelemetryEventType.SCORING_CALIBRATION_PROPOSED: {
            "current_version": 1,
            "feedback_count": 5,
            "proposed_changes": {},
            "created_at": "t",
        },
        TelemetryEventType.SCORING_CONFIG_CHANGED: {
            "old_version": 1,
            "new_version": 2,
            "action": "CONFIRM",
            "occurred_at": "t",
        },
        TelemetryEventType.INTEL_ITEM_ACTION: {
            "item_id": "i",
            "action": "READ",
            "occurred_at": "t",
        },
        TelemetryEventType.EXPANSION_SEARCH_FINISHED: {
            "item_id": "i",
            "result_count": 1,
            "qualified_count": 1,
            "duration": 1,
            "status": "SUCCESS",
        },
    }
    for event_type, payload in payloads.items():
        recorder.record(event_type, payload, created_at=NOW, run_id="r")

    rows = recorder.list("r")
    assert len(rows) == 12
    assert {row["event_type"] for row in rows} == {item.value for item in TelemetryEventType}


def test_p6_tc_06_scored_events_use_the_formal_daily_tier(runtime) -> None:  # type: ignore[no-untyped-def]
    for index in range(11):
        add_candidate(
            runtime,
            f"telemetry-tier-{index:02d}",
            title=f"Telemetry tier candidate {index:02d}",
            content=f"Distinct product capability {index:02d} for tier verification.",
        )
    pipeline, telemetry, archive = build_pipeline(
        runtime,
        FakeClock(),
        {},
        DynamicLLM(),
    )

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)

    scored_tiers = [
        row["payload"]["tier"]
        for row in telemetry.list(result.run_id)
        if row["event_type"] == TelemetryEventType.INTEL_ITEM_SCORED.value
    ]
    archived_tiers = [record.tier.value for record in archive.list_formal_archive()]
    assert scored_tiers.count("MUST_READ") == archived_tiers.count("MUST_READ") == 10
    assert scored_tiers.count("IMPORTANT") == archived_tiers.count("IMPORTANT") == 1
    assert scored_tiers.count("EXTENDED") == archived_tiers.count("EXTENDED") == 0


def test_p6_tc_06_available_business_actions_emit_telemetry(runtime) -> None:  # type: ignore[no-untyped-def]
    add_candidate(
        runtime,
        "telemetry-actions",
        title="Telemetry action candidate",
        content="A candidate used to trigger feedback and archive actions.",
    )
    pipeline, telemetry, archive = build_pipeline(
        runtime,
        FakeClock(),
        {},
        DynamicLLM(),
    )
    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.MANUAL)
    assert result.status is PipelineRunStatus.SUCCEEDED
    score = runtime.intelligence_repository.list_scores_for_date(
        REPORT_DATE,
        runtime.intelligence_repository.get_active_config().version,
    )[0]
    calibration = CalibrationService(runtime.intelligence_repository, telemetry)
    for index in range(5):
        calibration.submit_feedback(
            score.score_id,
            reason=f"density feedback {index}",
            affected_dimension="information_density",
            content_features={"sample": index},
            removed=True,
            submitted_at=NOW + timedelta(seconds=index),
        )
    assessment = calibration.propose(user_initiated=True, proposed_at=NOW + timedelta(minutes=1))
    assert assessment.proposal is not None
    calibration.confirm(
        assessment.proposal.proposal_id,
        user_confirmed=True,
        confirmed_at=NOW + timedelta(minutes=2),
    )
    event_id = archive.list_formal_archive()[0].event_id
    archive.save_note(event_id, "local note")

    event_types = {row["event_type"] for row in telemetry.list()}
    assert TelemetryEventType.QUALITY_FEEDBACK_SUBMITTED.value in event_types
    assert TelemetryEventType.SCORING_CALIBRATION_PROPOSED.value in event_types
    assert TelemetryEventType.SCORING_CONFIG_CHANGED.value in event_types
    assert TelemetryEventType.INTEL_ITEM_ACTION.value in event_types


def test_p6_tc_07_source_failure_does_not_block_pipeline(runtime) -> None:  # type: ignore[no-untyped-def]
    successful = create_source(runtime, "Successful")
    failing = create_source(runtime, "Failing")
    collector = SelectiveCollector(failing.source_id)
    pipeline, telemetry, archive = build_pipeline(
        runtime,
        FakeClock(),
        {SourceType.WEB: collector},
        DynamicLLM(),
    )

    result = pipeline.run(REPORT_DATE, trigger=PipelineTrigger.SCHEDULED)

    assert result.status is PipelineRunStatus.SUCCEEDED
    assert (result.attempted_sources, result.successful_sources, result.failed_sources) == (2, 1, 1)
    assert result.archived_count == 1
    formal_archive = archive.list_formal_archive()
    assert len(formal_archive) == 1
    assert result.digest_id is not None
    digest = runtime.phase6_repository.get_digest(result.digest_id)
    assert digest.event_ids == tuple(row.event_id for row in formal_archive)
    assert "质量分" in digest.markdown
    assert "来源" in digest.markdown
    assert (runtime.data_dir / digest.markdown_path).read_text(encoding="utf-8") == digest.markdown
    source_events = [
        row for row in telemetry.list(result.run_id) if row["event_type"] == "source_fetch_finished"
    ]
    assert {row["payload"]["source_id"] for row in source_events} == {
        successful.source_id,
        failing.source_id,
    }
    event_types = [row["event_type"] for row in telemetry.list(result.run_id)]
    assert event_types[0] == TelemetryEventType.PIPELINE_RUN_STARTED.value
    assert event_types[-1] == TelemetryEventType.PIPELINE_RUN_FINISHED.value
    assert event_types.index(TelemetryEventType.SOURCE_FETCH_FINISHED.value) < event_types.index(
        TelemetryEventType.INTEL_CHANGE_DETECTED.value
    )
    assert event_types.index(TelemetryEventType.INTEL_CHANGE_DETECTED.value) < event_types.index(
        TelemetryEventType.INTEL_ITEM_SCORED.value
    )
    assert event_types.index(TelemetryEventType.INTEL_ITEM_SCORED.value) < event_types.index(
        TelemetryEventType.DAILY_DIGEST_GENERATED.value
    )


def test_p6_tc_08_missing_config_and_secret_values_are_redacted(runtime) -> None:  # type: ignore[no-untyped-def]
    selection = DailySelectionService(runtime.intelligence_repository).select(
        REPORT_DATE, selected_at=NOW
    )
    digest = runtime.phase6_repository.save_digest(
        report_date=REPORT_DATE,
        selection_run_id=selection.selection_run_id,
        markdown="local digest remains available",
        event_ids=(),
        tier_counts={"MUST_READ": 0, "IMPORTANT": 0, "EXTENDED": 0},
        topic_order=(),
        created_at=NOW,
    )
    with pytest.raises(MissingConfigurationError) as missing:
        DeliveryService(
            runtime.phase6_repository,
            TelemetryRecorder(runtime.engine),
        ).push(digest.digest_id, pushed_at=NOW)
    assert str(missing.value) == "Missing required configuration: FEISHU_APP_ID"

    source = create_source(runtime, "SecretFailure")
    CollectionService(
        runtime.source_repository,
        {SourceType.WEB: SelectiveCollector(source.source_id, secret_error=True)},
    ).run(NOW)
    failures = runtime.source_repository.list_failures()
    serialized = json.dumps(failures)
    assert "super-secret" not in serialized
    assert "abc123" not in serialized
    assert "session456" not in serialized
    assert "[REDACTED]" in serialized

    recorder = TelemetryRecorder(runtime.engine)
    recorder.record(
        TelemetryEventType.INTEL_ITEM_ACTION,
        {
            "item_id": "i",
            "action": "Authorization: Bearer hidden-value",
            "occurred_at": "t",
            "api_token": "plain-secret",
        },
        created_at=NOW,
    )
    telemetry_json = json.dumps(recorder.list())
    assert "hidden-value" not in telemetry_json
    assert "plain-secret" not in telemetry_json

    for header_value, secret in (
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        (
            'authorization=Digest username="user", response="digest-secret"',
            "digest-secret",
        ),
        ("Proxy-Authorization: Bearer proxy-secret", "proxy-secret"),
    ):
        recorder.record(
            TelemetryEventType.INTEL_ITEM_ACTION,
            {
                "item_id": "auth-test",
                "action": header_value,
                "occurred_at": "t",
            },
            created_at=NOW,
        )
        assert secret not in json.dumps(recorder.list())
