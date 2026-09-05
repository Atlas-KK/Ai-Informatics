import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError, IntegrityError

from ai_intel.infrastructure.db.engine import create_sqlite_engine
from ai_intel.infrastructure.db.migrations import (
    MigrationSafetyError,
    downgrade_database,
    upgrade_database,
)


def test_empty_schema_upgrades_downgrades_and_rebuilds(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"events", "event_versions", "raw_snapshots", "deletion_audits"} <= tables
        with engine.connect() as connection:
            triggers = {
                str(name)
                for name in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='trigger'")
                ).scalars()
            }
        assert "prevent_scoring_config_content_update" in triggers
        assert "prevent_formal_event_field_update" in triggers
        assert "validate_event_aggregate_version_update" in triggers
        assert "prevent_event_aggregate_stable_key_update" in triggers
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO raw_snapshots "
                        "(snapshot_id, version_id, source_id, content_hash, raw_path, "
                        "first_seen_at) "
                        "VALUES ('snapshot', 'missing', 'source', 'hash', 'raw/x', '2026-09-03')"
                    )
                )
    finally:
        engine.dispose()

    downgrade_database(database)
    with sqlite3.connect(database) as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
            )
        }
    assert remaining == set()

    upgrade_database(database)
    assert "events" in inspect(create_sqlite_engine(database)).get_table_names()


def test_populated_database_refuses_implicit_destructive_downgrade(
    runtime, archive_service
) -> None:  # type: ignore[no-untyped-def]
    from tests.phase2.conftest import make_candidate

    archive_service.commit(make_candidate())
    with pytest.raises(MigrationSafetyError):
        downgrade_database(runtime.database_path)


def test_downgrade_refuses_when_only_deletion_audit_remains(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    from tests.phase2.conftest import make_candidate

    candidate = make_candidate()
    archive_service.commit(candidate)
    archive_service.move_to_trash(candidate.event_id, "Migration safety regression")
    archive_service.permanently_delete(candidate.event_id, confirmed=True)

    with pytest.raises(MigrationSafetyError, match="deletion_audits"):
        downgrade_database(runtime.database_path)

    downgrade_database(runtime.database_path, allow_data_loss=True)
    with sqlite3.connect(runtime.database_path) as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
            )
        }
    assert remaining == set()


def test_database_trigger_rejects_immutable_version_update(runtime, archive_service) -> None:  # type: ignore[no-untyped-def]
    from tests.phase2.conftest import make_candidate

    archive_service.commit(make_candidate())
    with pytest.raises(DatabaseError, match="append-only"):
        with runtime.engine.begin() as connection:
            connection.execute(text("UPDATE event_versions SET content='tampered'"))
