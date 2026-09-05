# ruff: noqa: E501
"""Add Phase 6 pipeline, digest, outbox and local telemetry.

Revision ID: 0008_phase6_pipeline_delivery
Revises: 0007_phase5_regression_fixes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_phase6_pipeline_delivery"
down_revision: str | None = "0007_phase5_regression_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("report_date", sa.String(10), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("window_start", sa.String(40), nullable=False),
        sa.Column("window_end", sa.String(40), nullable=False),
        sa.Column("deadline_at", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("owner_pid", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("heartbeat_at", sa.String(40), nullable=False),
        sa.Column("finished_at", sa.String(40)),
        sa.Column("attempted_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(50)),
        sa.CheckConstraint("trigger_type IN ('SCHEDULED','CATCH_UP','MANUAL')"),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','TIMED_OUT','WAITING_RETRY','REJECTED_DUPLICATE')"
        ),
        sa.CheckConstraint(
            "attempted_sources >= 0 AND successful_sources >= 0 AND failed_sources >= 0 AND archived_count >= 0 AND pending_count >= 0"
        ),
    )
    op.create_table(
        "pipeline_lock",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_pid", sa.Integer(), nullable=False),
        sa.Column("acquired_at", sa.String(40), nullable=False),
        sa.Column("heartbeat_at", sa.String(40), nullable=False),
        sa.CheckConstraint("singleton_id = 1"),
    )
    op.create_table(
        "pipeline_work_items",
        sa.Column("work_item_id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("run_id", "aggregate_version_id"),
        sa.CheckConstraint("stage IN ('PROCESSING','SCORING','ARCHIVE')"),
        sa.CheckConstraint("status IN ('PENDING','COMPLETED','WAITING_RETRY')"),
    )
    op.create_table(
        "daily_digests",
        sa.Column("digest_id", sa.String(36), primary_key=True),
        sa.Column("report_date", sa.String(10), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "selection_run_id",
            sa.String(36),
            sa.ForeignKey("daily_selection_runs.selection_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("markdown_path", sa.Text(), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("event_ids_json", sa.Text(), nullable=False),
        sa.Column("tier_counts_json", sa.Text(), nullable=False),
        sa.Column("topic_order_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("report_date", "version_no"),
        sa.CheckConstraint("version_no > 0"),
    )
    op.create_table(
        "delivery_segments",
        sa.Column("segment_id", sa.String(36), primary_key=True),
        sa.Column(
            "digest_id",
            sa.String(36),
            sa.ForeignKey("daily_digests.digest_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("segment_no", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("digest_id", "segment_no"),
        sa.CheckConstraint("segment_no > 0"),
        sa.CheckConstraint("attempt_count >= 0"),
        sa.CheckConstraint("status IN ('PENDING','SENT','FAILED')"),
    )
    op.create_table(
        "telemetry_events",
        sa.Column("telemetry_event_id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("run_id", sa.String(36)),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    for table_name in ("daily_digests", "telemetry_events"):
        op.execute(
            f"CREATE TRIGGER prevent_{table_name}_update BEFORE UPDATE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
        )
        op.execute(
            f"CREATE TRIGGER prevent_{table_name}_delete BEFORE DELETE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
        )


def downgrade() -> None:
    for table_name in ("telemetry_events", "daily_digests"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_delete")
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_update")
    for table_name in (
        "telemetry_events",
        "delivery_segments",
        "daily_digests",
        "pipeline_work_items",
        "pipeline_lock",
        "pipeline_runs",
    ):
        op.drop_table(table_name)
