"""Add Phase 3 source collection and Manual Inbox persistence.

Revision ID: 0003_phase3_sources
Revises: 0002_phase2_invariant_triggers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3_sources"
down_revision: str | None = "0002_phase2_invariant_triggers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_configs",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("authority_level", sa.Integer(), nullable=False),
        sa.Column("truncate_chars", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("deleted_at", sa.String(40)),
        sa.CheckConstraint("source_type IN ('WEB','RSS','GITHUB','VIDEO')"),
        sa.CheckConstraint("authority_level BETWEEN 1 AND 5"),
        sa.CheckConstraint("truncate_chars IN (10000,20000,50000)"),
        sa.CheckConstraint("state IN ('ACTIVE','PAUSED','DELETED')"),
    )
    op.create_index("ix_source_configs_state", "source_configs", ["state"])
    op.create_table(
        "expert_whitelist",
        sa.Column("expert_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("deleted_at", sa.String(40)),
        sa.CheckConstraint("state IN ('ACTIVE','PAUSED','DELETED')"),
    )
    op.create_table(
        "expert_source_links",
        sa.Column(
            "expert_id",
            sa.String(36),
            sa.ForeignKey("expert_whitelist.expert_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("source_configs.source_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "collection_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("window_start", sa.String(40), nullable=False),
        sa.Column("window_end", sa.String(40), nullable=False),
        sa.Column("automatic_source_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint("automatic_source_count >= 0"),
        sa.CheckConstraint("status IN ('PLANNED','FINISHED')"),
    )
    op.create_table(
        "collection_failures",
        sa.Column("failure_id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("collection_runs.run_id", ondelete="RESTRICT"),
        ),
        sa.Column("source_id", sa.String(36)),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("stage IN ('FETCH','EXTRACT','RANKING','IMPORT')"),
        sa.CheckConstraint("retry_count >= 0"),
    )
    op.create_index("ix_collection_failures_run", "collection_failures", ["run_id"])
    op.create_table(
        "collected_raw_snapshots",
        sa.Column("snapshot_id", sa.String(36), primary_key=True),
        sa.Column("import_key", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("collection_runs.run_id", ondelete="RESTRICT"),
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text()),
        sa.Column("published_at", sa.String(40), nullable=False),
        sa.Column("published_at_unknown", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False, unique=True),
        sa.Column("model_input", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("source_type IN ('WEB','RSS','GITHUB','VIDEO','MANUAL_INBOX')"),
        sa.CheckConstraint("status IN ('COLLECTED','METADATA_ONLY')"),
    )
    op.create_index(
        "ix_collected_raw_source_created",
        "collected_raw_snapshots",
        ["source_id", "created_at"],
    )
    op.create_table(
        "source_metric_snapshots",
        sa.Column("snapshot_id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("subject_key", sa.Text(), nullable=False),
        sa.Column("metric_type", sa.String(30), nullable=False),
        sa.Column("observed_at", sa.String(40), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("response_id", sa.Text(), nullable=False),
        sa.UniqueConstraint("subject_key", "metric_type", "observed_at"),
        sa.CheckConstraint("value >= 0"),
    )
    op.create_index(
        "ix_metric_subject_time",
        "source_metric_snapshots",
        ["subject_key", "metric_type", "observed_at"],
    )
    op.create_table(
        "manual_inbox_imports",
        sa.Column("import_id", sa.String(36), primary_key=True),
        sa.Column("file_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(36)),
        sa.Column("imported_at", sa.String(40), nullable=False),
        sa.CheckConstraint("status IN ('IMPORTED','DUPLICATE','FAILED')"),
        sa.CheckConstraint("retry_count >= 0"),
    )
    op.execute(
        """
        CREATE TRIGGER prevent_collected_raw_update
        BEFORE UPDATE ON collected_raw_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'collected raw snapshots are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_collected_raw_delete
        BEFORE DELETE ON collected_raw_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'collected raw snapshots are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_source_metric_update
        BEFORE UPDATE ON source_metric_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'source metric snapshots are append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_source_metric_delete
        BEFORE DELETE ON source_metric_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'source metric snapshots are append-only');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prevent_collected_raw_delete")
    op.execute("DROP TRIGGER IF EXISTS prevent_collected_raw_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_source_metric_delete")
    op.execute("DROP TRIGGER IF EXISTS prevent_source_metric_update")
    op.drop_table("manual_inbox_imports")
    op.drop_index("ix_metric_subject_time", table_name="source_metric_snapshots")
    op.drop_table("source_metric_snapshots")
    op.drop_index("ix_collected_raw_source_created", table_name="collected_raw_snapshots")
    op.drop_table("collected_raw_snapshots")
    op.drop_index("ix_collection_failures_run", table_name="collection_failures")
    op.drop_table("collection_failures")
    op.drop_table("collection_runs")
    op.drop_table("expert_source_links")
    op.drop_table("expert_whitelist")
    op.drop_index("ix_source_configs_state", table_name="source_configs")
    op.drop_table("source_configs")
