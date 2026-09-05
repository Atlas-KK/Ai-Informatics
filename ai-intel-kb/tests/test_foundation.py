import sqlite3

from ai_intel.config import Settings
from ai_intel.foundation import RUNTIME_SUBDIRECTORIES, close_runtime, initialize_runtime


def test_migrated_database_and_runtime_boundaries_start(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runtime = initialize_runtime(Settings(data_dir=tmp_path))
    try:
        assert runtime.database_path.exists()
        assert all((tmp_path / name).is_dir() for name in RUNTIME_SUBDIRECTORIES)

        with sqlite3.connect(runtime.database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        assert {"alembic_version", "events", "event_versions", "staged_commits"} <= tables
    finally:
        close_runtime(runtime)
