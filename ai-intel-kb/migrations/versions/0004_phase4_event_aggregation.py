# ruff: noqa: E501
"""Add Phase 4 deterministic event aggregation persistence.

Revision ID: 0004_phase4_event_aggregation
Revises: 0003_phase3_sources
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4_event_aggregation"
down_revision: str | None = "0003_phase3_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_aggregates",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("stable_key", sa.String(64), nullable=False, unique=True),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("current_version > 0"),
    )
    op.create_table(
        "event_match_keys",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("key_kind", sa.String(20), primary_key=True),
        sa.Column("key_value", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("key_kind", "key_value"),
        sa.CheckConstraint("key_kind IN ('URL','CONTENT','TITLE_ENTITIES')"),
    )
    op.create_table(
        "aggregate_versions",
        sa.Column("aggregate_version_id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("change_reasons_json", sa.Text(), nullable=False),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("entities_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("event_id", "version_no"),
        sa.CheckConstraint("version_no > 0"),
        sa.CheckConstraint("change_type IN ('NEW_EVENT','UPDATED')"),
    )
    op.create_table(
        "aggregate_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "upstream_snapshot_id",
            sa.String(36),
            sa.ForeignKey("collected_raw_snapshots.snapshot_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.String(40), nullable=False),
        sa.Column("viewpoint", sa.Text(), nullable=False),
        sa.Column("normalized_viewpoint", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("aggregate_version_id", "upstream_snapshot_id"),
    )
    op.create_table(
        "aggregate_viewpoints",
        sa.Column("viewpoint_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("normalized_statement", sa.Text(), nullable=False),
        sa.Column("source_ids_json", sa.Text(), nullable=False),
        sa.Column("supporting_source_count", sa.Integer(), nullable=False),
        sa.Column("valid_source_count", sa.Integer(), nullable=False),
        sa.Column("source_coverage_ratio", sa.Float(), nullable=False),
        sa.UniqueConstraint("aggregate_version_id", "normalized_statement"),
        sa.CheckConstraint(
            "supporting_source_count > 0 AND valid_source_count > 0 AND supporting_source_count <= valid_source_count"
        ),
        sa.CheckConstraint("source_coverage_ratio >= 0 AND source_coverage_ratio <= 1"),
    )
    op.create_table(
        "daily_event_candidates",
        sa.Column("candidate_id", sa.String(36), primary_key=True),
        sa.Column("report_date", sa.String(10), nullable=False),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("event_aggregates.event_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("needs_scoring", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("report_date", "event_id"),
        sa.CheckConstraint("change_type IN ('NEW_EVENT','UPDATED')"),
    )
    op.create_table(
        "aggregation_audits",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36)),
        sa.Column("snapshot_ids_json", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("change_type IN ('NEW_EVENT','UPDATED','NO_CHANGE','IGNORED')"),
    )
    for table in (
        "event_match_keys",
        "aggregate_versions",
        "aggregate_evidence",
        "aggregate_viewpoints",
        "aggregation_audits",
    ):
        op.execute(f"""
            CREATE TRIGGER prevent_{table}_update BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END
        """)
        op.execute(f"""
            CREATE TRIGGER prevent_{table}_delete BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END
        """)


def downgrade() -> None:
    for table in (
        "event_match_keys",
        "aggregate_versions",
        "aggregate_evidence",
        "aggregate_viewpoints",
        "aggregation_audits",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table}_delete")
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table}_update")
    op.drop_table("aggregation_audits")
    op.drop_table("daily_event_candidates")
    op.drop_table("aggregate_viewpoints")
    op.drop_table("aggregate_evidence")
    op.drop_table("aggregate_versions")
    op.drop_table("event_match_keys")
    op.drop_table("event_aggregates")
