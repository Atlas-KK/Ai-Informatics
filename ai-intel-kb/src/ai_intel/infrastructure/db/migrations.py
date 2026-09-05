"""Programmatic Alembic entry points with explicit destructive downgrade consent."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, func, inspect, select

from ai_intel.infrastructure.db.engine import create_sqlite_engine


class MigrationSafetyError(RuntimeError):
    pass


DESTRUCTIVE_DATA_TABLES = (
    "events",
    "event_versions",
    "raw_snapshots",
    "evidence",
    "scores",
    "user_metadata",
    "notes",
    "scoring_configs",
    "active_scoring_config",
    "staged_commits",
    "record_locks",
    "recovery_audits",
    "deletion_audits",
    "projection_manifests",
    "source_configs",
    "expert_whitelist",
    "expert_source_links",
    "collection_runs",
    "collection_failures",
    "collected_raw_snapshots",
    "source_metric_snapshots",
    "manual_inbox_imports",
    "event_aggregates",
    "event_match_keys",
    "aggregate_versions",
    "aggregate_evidence",
    "aggregate_viewpoints",
    "daily_event_candidates",
    "aggregation_audits",
    "ai_processing_results",
    "ai_processing_failures",
    "candidate_scores",
    "daily_selection_runs",
    "daily_selections",
    "formalization_links",
    "quality_feedback",
    "calibration_proposals",
    "calibration_decisions",
    "scoring_config_audits",
    "topic_ideas",
    "pipeline_runs",
    "pipeline_lock",
    "pipeline_work_items",
    "daily_digests",
    "delivery_segments",
    "telemetry_events",
    "ui_settings",
    "extension_search_runs",
    "extension_search_results",
)


def _config(database_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[4]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"
    )
    return config


def upgrade_database(database_path: Path, revision: str = "head") -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_config(database_path), revision)


def downgrade_database(
    database_path: Path,
    revision: str = "base",
    *,
    allow_data_loss: bool = False,
) -> None:
    if database_path.exists() and not allow_data_loss:
        engine = create_sqlite_engine(database_path)
        try:
            existing_tables = set(inspect(engine).get_table_names())
            populated_tables: list[str] = []
            with engine.connect() as connection:
                for table_name in DESTRUCTIVE_DATA_TABLES:
                    if table_name not in existing_tables:
                        continue
                    table = Table(table_name, MetaData(), autoload_with=connection)
                    count_statement = select(func.count()).select_from(table)
                    if table_name == "ui_settings":
                        count_statement = count_statement.where(
                            table.c.updated_at != "2026-09-04T00:00:00+00:00"
                        )
                    count = connection.execute(count_statement).scalar_one()
                    if count:
                        populated_tables.append(table_name)
            if populated_tables:
                names = ", ".join(populated_tables)
                raise MigrationSafetyError(
                    "Refusing destructive downgrade while persisted data exists in: "
                    f"{names}. Create a verified backup or pass explicit data-loss consent."
                )
        finally:
            engine.dispose()
    command.downgrade(_config(database_path), revision)
