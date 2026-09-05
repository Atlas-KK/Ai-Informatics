import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from ai_intel.domain.models import EvidenceInput, ScoreInput, content_digest
from ai_intel.domain.states import ReadState, Tier
from ai_intel.infrastructure.archive.commit import FailurePoint, InjectedCommitFailure
from ai_intel.infrastructure.db.repository import ArchiveInvariantError, ReadOnlyArchiveError
from ai_intel.infrastructure.db.schema import event_versions, evidence, scores, scoring_configs
from tests.phase2.conftest import make_candidate


def test_staged_commit_reconciles_sqlite_raw_archive_and_flat_yaml(
    runtime, archive_service
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate()
    record = archive_service.commit(candidate)

    raw_path = runtime.data_dir / record.raw_path
    archive_path = runtime.data_dir / record.archive_path
    markdown = archive_path.read_text(encoding="utf-8")

    assert raw_path.read_text(encoding="utf-8") == candidate.raw_content
    assert content_digest(raw_path.read_text(encoding="utf-8")) == record.raw_hash
    assert f'event_id: "{candidate.event_id}"' in markdown
    assert "version_no: 1" in markdown
    assert f'primary_topic: "{candidate.primary_topic}"' in markdown
    assert 'source_ids: ["source-primary","source-secondary"]' in markdown
    assert "quality_score: 90.0" in markdown
    assert "score_version: 1" in markdown
    assert f'content_hash: "{candidate.content_hash}"' in markdown
    assert json.loads(json.dumps(record.source_ids)) == list(candidate.source_ids)
    with runtime.engine.connect() as connection:
        source_time = connection.execute(
            select(evidence.c.published_at_original, evidence.c.published_timezone).limit(1)
        ).one()
    assert source_time.published_at_original.endswith("+00:00")
    assert source_time.published_timezone == "+0000"


def test_processing_is_hidden_and_user_data_survives_new_version(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    first = make_candidate()
    archive_service.commit(first)
    archive_service.save_note(first.event_id, "My independent note")
    archive_service.update_user_metadata(
        first.event_id,
        favorite=True,
        pinned=True,
        read_state=ReadState.READ,
    )

    with pytest.raises(ReadOnlyArchiveError):
        runtime.repository.reject_system_update(first.event_id, canonical_title="edited")

    processing = make_candidate(
        event_id="00000000-0000-4000-8000-000000000099",
        snapshot_id="10000000-0000-4000-8000-000000000099",
    )
    with pytest.raises(InjectedCommitFailure):
        archive_service.commit(processing, fail_at=FailurePoint.SQLITE_STAGED)
    assert {item.event_id for item in archive_service.list_formal_archive()} == {first.event_id}

    second = make_candidate(
        event_id=first.event_id,
        snapshot_id="10000000-0000-4000-8000-000000000002",
        version_no=2,
        content="Authoritative content version 2.",
    )
    archive_service.commit(second)
    assert runtime.repository.get_note(first.event_id) == "My independent note"
    metadata = runtime.repository.get_user_metadata(first.event_id)
    assert metadata.favorite is True
    assert metadata.pinned is True
    assert metadata.read_state is ReadState.READ

    runtime.repository.add_score(
        first.event_id,
        2,
        ScoreInput(
            config_version=2,
            dimensions={"authority": 95.0},
            total=94.0,
            tier=Tier.MUST_READ,
        ),
    )
    with runtime.engine.connect() as connection:
        score_count = connection.execute(
            select(func.count())
            .select_from(scores.join(event_versions))
            .where(event_versions.c.event_id == first.event_id)
        ).scalar_one()
        assert score_count == 3
    assert runtime.repository.get_ready(first.event_id).quality_score == 94.0


def test_formal_threshold_and_scoring_configuration_activation_require_confirmation(
    runtime,
) -> None:  # type: ignore[no-untyped-def]
    low_score = ScoreInput(
        config_version=1,
        dimensions={"authority": 60.0},
        total=69.0,
        tier=Tier.EXTENDED,
    )
    with pytest.raises(ValueError, match="at least 70"):
        replace(make_candidate(), score=low_score)

    runtime.repository.add_scoring_config(1, {"authority": 1.0}, {})
    runtime.repository.add_scoring_config(2, {"authority": 0.8}, {"source-a": 1.1})
    with pytest.raises(ArchiveInvariantError, match="requires user confirmation"):
        runtime.repository.activate_scoring_config(2, user_confirmed=False)
    runtime.repository.activate_scoring_config(2, user_confirmed=True)
    assert runtime.repository.get_active_scoring_version() == 2
    with runtime.engine.connect() as connection:
        config_count = connection.execute(
            select(func.count()).select_from(scoring_configs)
        ).scalar_one()
        active_status = connection.execute(
            select(scoring_configs.c.status).where(scoring_configs.c.config_version == 2)
        ).scalar_one()
    assert config_count == 2
    assert active_status == "ACTIVE"


def test_ready_source_ids_match_deduplicated_markdown_relationships(
    runtime, archive_service
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate()
    candidate = replace(
        candidate,
        evidence=(
            EvidenceInput(
                source_id="source-primary",
                url="https://primary.test/first",
                published_at=candidate.created_at,
                viewpoint="First relationship.",
            ),
            EvidenceInput(
                source_id="source-primary",
                url="https://primary.test/second",
                published_at=candidate.created_at,
                viewpoint="Second relationship.",
            ),
        ),
    )

    record = archive_service.commit(candidate)
    markdown = (runtime.data_dir / record.archive_path).read_text(encoding="utf-8")

    assert record.source_ids == candidate.source_ids == ("source-primary",)
    assert 'source_ids: ["source-primary"]' in markdown


def test_ready_list_uses_constant_query_count(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    for _ in range(10):
        archive_service.commit(make_candidate(event_id=str(uuid4()), snapshot_id=str(uuid4())))

    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    event.listen(runtime.engine, "before_cursor_execute", record_statement)
    try:
        records = archive_service.list_formal_archive()
    finally:
        event.remove(runtime.engine, "before_cursor_execute", record_statement)

    assert len(records) == 10
    assert len(statements) <= 3
