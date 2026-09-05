import json
from datetime import date, timedelta
from hashlib import sha256
from itertools import permutations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError

from ai_intel.application.event_aggregation import EventAggregationService
from ai_intel.domain.event_matching import (
    connected_components,
    match_snapshots,
    stable_event_identity,
)
from ai_intel.domain.fingerprint import CandidateOrigin, SnapshotDraft, normalize_snapshot
from ai_intel.domain.source import SourceType
from ai_intel.domain.versioning import ChangeReason, ChangeType
from ai_intel.infrastructure.db.schema import (
    aggregate_evidence,
    aggregate_versions,
    aggregate_viewpoints,
    aggregation_audits,
    daily_event_candidates,
    event_aggregates,
    events,
)
from tests.phase4.conftest import OBSERVED, add_snapshot

REPORT_DATE = date(2026, 9, 3)


def service(runtime):  # type: ignore[no-untyped-def]
    return EventAggregationService(runtime.event_repository)


def count(runtime, table) -> int:  # type: ignore[no-untyped-def]
    with runtime.engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def test_p4_tc_01_matching_is_stable_and_one_daily_candidate(runtime) -> None:  # type: ignore[no-untyped-def]
    ids = (
        add_snapshot(runtime, "url-a"),
        add_snapshot(
            runtime,
            "url-b",
            source_id="source-b",
            url="https://news.example.test/agent-kit?utm_source=daily#top",
            content="Independent report with different words.",
        ),
        add_snapshot(
            runtime,
            "body-copy",
            source_id="source-c",
            url="https://mirror.example.test/story",
        ),
        add_snapshot(
            runtime,
            "title-variant",
            source_id="source-d",
            title="OpenAI releases the Agent Kit",
            url="https://fourth.example.test/story",
            content="Fourth independent account.",
        ),
    )
    normalized = tuple(
        normalize_snapshot(runtime.event_repository.load_snapshot_draft(snapshot_id))
        for snapshot_id in ids
    )
    identities = {
        stable_event_identity(connected_components(order)[0]) for order in permutations(normalized)
    }
    assert len(identities) == 1
    assert stable_event_identity((normalized[0],)) == stable_event_identity(normalized)
    result = service(runtime).process_snapshot_ids(
        ids, report_date=REPORT_DATE, observed_at=OBSERVED
    )
    assert len(result) == 1
    assert result[0].change_type is ChangeType.NEW_EVENT
    assert count(runtime, event_aggregates) == 1
    assert count(runtime, daily_event_candidates) == 1
    assert count(runtime, aggregate_evidence) == 4

    unrelated = normalize_snapshot(
        SnapshotDraft(
            "unrelated",
            "other",
            "OpenAI releases the Agent Kit",
            "https://unrelated.example.test/item",
            None,
            OBSERVED,
            "Completely unrelated body.",
            "Different claim",
            ("Different entity",),
        )
    )
    assert not match_snapshots(normalized[0], unrelated).matched
    false_miss_risk = normalize_snapshot(
        SnapshotDraft(
            "false-miss-risk",
            "other-source",
            "New orchestration workflow ships",
            "https://risk.example.test/item",
            None,
            OBSERVED,
            "A separately worded account of the same release.",
            "Agent Kit improves orchestration",
            ("OpenAI", "Agent Kit"),
        )
    )
    assert not match_snapshots(normalized[0], false_miss_risk).matched


def test_p4_tc_02_viewpoint_coverage_is_source_ratio_not_confidence(runtime) -> None:  # type: ignore[no-untyped-def]
    ids = tuple(
        add_snapshot(
            runtime,
            f"view-{index}",
            source_id=f"source-{index}",
            url=f"https://source-{index}.example.test/item",
            viewpoint="Supports adoption" if index < 3 else "Questions adoption",
        )
        for index in range(4)
    )
    service(runtime).process_snapshot_ids(ids, report_date=REPORT_DATE, observed_at=OBSERVED)
    rows = runtime.event_repository.table_rows(aggregate_viewpoints)
    by_statement = {str(row["statement"]): row for row in rows}
    assert by_statement["Supports adoption"]["source_coverage_ratio"] == 0.75
    assert by_statement["Questions adoption"]["source_coverage_ratio"] == 0.25
    assert all(row["valid_source_count"] == 4 for row in rows)
    assert all("confidence" not in row for row in rows)
    assert json.loads(str(by_statement["Supports adoption"]["source_ids_json"])) == [
        "source-0",
        "source-1",
        "source-2",
    ]


def test_p4_tc_03_material_changes_append_versions_and_preserve_history(runtime) -> None:  # type: ignore[no-untyped-def]
    app = service(runtime)
    first = add_snapshot(runtime, "base")
    initial = app.process_snapshot_ids((first,), report_date=REPORT_DATE, observed_at=OBSERVED)[0]
    event_id = initial.event_id
    before = runtime.event_repository.table_rows(aggregate_versions)

    fact = add_snapshot(
        runtime,
        "new-fact",
        content="Agent Kit adds deterministic orchestration and audit logs.",
        entities=("OpenAI", "Agent Kit", "Audit logs"),
    )
    viewpoint = add_snapshot(
        runtime,
        "new-viewpoint",
        content="Agent Kit adds deterministic orchestration and audit logs.",
        viewpoint="Audit logs may increase storage cost",
        entities=("OpenAI", "Agent Kit", "Audit logs"),
    )
    new_source = add_snapshot(
        runtime,
        "new-source",
        source_id="source-b",
        url="https://second.example.test/agent-kit",
        content="Agent Kit adds deterministic orchestration and audit logs.",
        viewpoint="Audit logs may increase storage cost",
        entities=("OpenAI", "Agent Kit", "Audit logs"),
    )
    changed = add_snapshot(
        runtime,
        "content-change",
        source_id="source-b",
        url="https://second.example.test/agent-kit",
        content="Agent Kit audit logs are now generally available.",
        viewpoint="Audit logs may increase storage cost",
        entities=("OpenAI", "Agent Kit", "Audit logs"),
    )
    results = [
        app.process_snapshot_ids((snapshot,), report_date=REPORT_DATE, observed_at=OBSERVED)[0]
        for snapshot in (fact, viewpoint, new_source, changed)
    ]
    assert all(result.event_id == event_id for result in results)
    assert [result.version_no for result in results] == [2, 3, 4, 5]
    assert ChangeReason.NEW_FACT in results[0].reasons
    assert ChangeReason.NEW_VIEWPOINT in results[1].reasons
    assert ChangeReason.NEW_SOURCE in results[2].reasons
    assert ChangeReason.CONTENT_CHANGE in results[3].reasons
    assert runtime.event_repository.table_rows(aggregate_versions)[0] == before[0]
    assert count(runtime, daily_event_candidates) == 1

    reverted = add_snapshot(
        runtime,
        "content-reversion",
        source_id="source-b",
        url="https://second.example.test/agent-kit",
        content="Agent Kit adds deterministic orchestration and audit logs.",
        viewpoint="Audit logs may increase storage cost",
        entities=("OpenAI", "Agent Kit", "Audit logs"),
    )
    reversion = app.process_snapshot_ids(
        (reverted,), report_date=REPORT_DATE, observed_at=OBSERVED
    )[0]
    assert reversion.version_no == 6
    assert ChangeReason.CONTENT_CHANGE in reversion.reasons


def test_p4_tc_04_time_and_equivalent_markup_do_not_create_version(runtime) -> None:  # type: ignore[no-untyped-def]
    app = service(runtime)
    first = add_snapshot(runtime, "time-1", content="<article>Signal body</article>")
    app.process_snapshot_ids((first,), report_date=REPORT_DATE, observed_at=OBSERVED)
    second = add_snapshot(
        runtime,
        "time-2",
        content="  <article> Signal   body </article>  ",
        published_at=OBSERVED + timedelta(hours=2),
    )
    result = app.process_snapshot_ids(
        (second,), report_date=REPORT_DATE, observed_at=OBSERVED + timedelta(hours=2)
    )[0]
    assert result.change_type is ChangeType.NO_CHANGE
    assert result.needs_scoring is False
    assert count(runtime, aggregate_versions) == 1
    assert count(runtime, daily_event_candidates) == 1
    assert count(runtime, events) == 0


def test_p4_tc_05_extension_and_manual_link_existing_without_duplicate(runtime) -> None:  # type: ignore[no-untyped-def]
    app = service(runtime)
    base = add_snapshot(runtime, "base-link")
    original = app.process_snapshot_ids((base,), report_date=REPORT_DATE, observed_at=OBSERVED)[0]
    extension = add_snapshot(
        runtime,
        "extension",
        url="https://search.example.test/result",
    )
    ignored = app.process_snapshot_ids(
        (extension,),
        report_date=REPORT_DATE,
        observed_at=OBSERVED,
        origin=CandidateOrigin.EXTENDED_SEARCH,
        selected_for_ingestion=False,
    )[0]
    assert ignored.change_type is ChangeType.IGNORED
    selected = app.process_snapshot_ids(
        (extension,),
        report_date=REPORT_DATE,
        observed_at=OBSERVED,
        origin=CandidateOrigin.EXTENDED_SEARCH,
    )[0]
    assert selected.change_type is ChangeType.UPDATED
    assert ChangeReason.NEW_EVIDENCE in selected.reasons
    manual = add_snapshot(
        runtime,
        "manual",
        source_id="manual-inbox",
        source_type=SourceType.MANUAL_INBOX,
        url="https://manual.example.test/copied-item",
    )
    manual_result = app.process_snapshot_ids(
        (manual,), report_date=REPORT_DATE, observed_at=OBSERVED
    )[0]
    assert selected.event_id == manual_result.event_id == original.event_id
    current = runtime.event_repository.get_current_state(str(original.event_id))
    assert current is not None
    assert {item.snapshot_id for item in current.evidence} == {base, extension, manual}
    assert count(runtime, event_aggregates) == 1
    assert count(runtime, daily_event_candidates) == 1
    assert count(runtime, events) == 0


def test_p4_tc_06_traceability_append_only_and_repeatability(runtime) -> None:  # type: ignore[no-untyped-def]
    app = service(runtime)
    base = add_snapshot(runtime, "trace-base")
    created = app.process_snapshot_ids((base,), report_date=REPORT_DATE, observed_at=OBSERVED)[0]
    update_id = add_snapshot(runtime, "trace-update", viewpoint="A conflicting viewpoint")
    updated = app.process_snapshot_ids((update_id,), report_date=REPORT_DATE, observed_at=OBSERVED)[
        0
    ]
    repeated = app.process_snapshot_ids(
        (update_id,), report_date=REPORT_DATE, observed_at=OBSERVED
    )[0]
    assert [created.change_type, updated.change_type, repeated.change_type] == [
        ChangeType.NEW_EVENT,
        ChangeType.UPDATED,
        ChangeType.NO_CHANGE,
    ]
    audits = runtime.event_repository.table_rows(aggregation_audits)
    assert [row["change_type"] for row in audits] == ["NEW_EVENT", "UPDATED", "NO_CHANGE"]
    evidence_rows = runtime.event_repository.table_rows(aggregate_evidence)
    raw_rows = {row["snapshot_id"]: row for row in runtime.source_repository.list_collected()}
    assert all(row["upstream_snapshot_id"] in raw_rows for row in evidence_rows)
    assert all(
        sha256(str(row["normalized_content"]).encode()).hexdigest() == row["content_hash"]
        for row in evidence_rows
    )
    assert count(runtime, events) == 0
    with pytest.raises(DatabaseError, match="append-only"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE aggregate_versions SET canonical_title='tampered'"))
    with pytest.raises(DatabaseError, match="current-version transition"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE event_aggregates SET current_version=999"))
    with pytest.raises(DatabaseError, match="stable key is immutable"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE event_aggregates SET stable_key='tampered'"))
