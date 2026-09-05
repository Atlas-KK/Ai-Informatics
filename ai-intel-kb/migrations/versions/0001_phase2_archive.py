"""Phase 2 authoritative archive schema.

Revision ID: 0001_phase2_archive
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase2_archive"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = ("raw_snapshots", "event_versions", "evidence", "scores", "scoring_configs")


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("primary_topic", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROCESSING','READY','WAITING_RETRY')", name="ck_event_status"
        ),
    )
    op.create_table(
        "scoring_configs",
        sa.Column("config_version", sa.Integer(), primary_key=True),
        sa.Column("weights_json", sa.Text(), nullable=False),
        sa.Column("source_overrides_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("config_version > 0", name="ck_scoring_version_positive"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_scoring_status"),
    )
    op.create_table(
        "deletion_audits",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("deletion_reason", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.String(40), nullable=False),
        sa.Column("version_count", sa.Integer(), nullable=False),
        sa.Column("content_hashes_json", sa.Text(), nullable=False),
        sa.CheckConstraint("version_count > 0", name="ck_deleted_version_count"),
    )
    op.create_table(
        "recovery_audits",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36)),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "projection_manifests",
        sa.Column("projection_version", sa.Integer(), primary_key=True),
        sa.Column("generated_at", sa.String(40), nullable=False),
        sa.Column("source_hashes_json", sa.Text(), nullable=False),
        sa.Column("target_paths_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "event_versions",
        sa.Column("version_id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(40), nullable=False),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("primary_topic", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("archive_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("event_id", "version_no", name="uq_event_version"),
        sa.CheckConstraint("version_no > 0", name="ck_version_positive"),
    )
    op.create_table(
        "user_metadata",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("read_state", sa.String(10), nullable=False),
        sa.Column("trash_state", sa.String(10), nullable=False),
        sa.Column("trash_reason", sa.Text()),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("read_state IN ('UNREAD','READ')", name="ck_read_state"),
        sa.CheckConstraint("trash_state IN ('ACTIVE','TRASHED')", name="ck_trash_state"),
        sa.CheckConstraint(
            "(trash_state = 'ACTIVE' AND trash_reason IS NULL) OR "
            "(trash_state = 'TRASHED' AND length(trim(trash_reason)) > 0)",
            name="ck_trash_reason",
        ),
    )
    op.create_table(
        "notes",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "active_scoring_config",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column(
            "config_version",
            sa.Integer(),
            sa.ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.String(40), nullable=False),
        sa.CheckConstraint("singleton_id = 1", name="ck_active_scoring_singleton"),
    )
    op.create_table(
        "staged_commits",
        sa.Column("commit_id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False),
        sa.Column("raw_stage_path", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("archive_path", sa.Text(), nullable=False),
        sa.Column("archive_stage_path", sa.Text(), nullable=False),
        sa.Column("archive_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("event_id", "version_no", name="uq_staged_event_version"),
        sa.CheckConstraint("state IN ('STAGED','READY','ERROR')", name="ck_commit_state"),
    )
    op.create_table(
        "record_locks",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.event_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_pid", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("acquired_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "raw_snapshots",
        sa.Column("snapshot_id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("event_versions.version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False, unique=True),
        sa.Column("first_seen_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("event_versions.version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.String(40), nullable=False),
        sa.Column("published_at_original", sa.String(40), nullable=False),
        sa.Column("published_timezone", sa.String(20), nullable=False),
        sa.Column("viewpoint", sa.Text(), nullable=False),
        sa.UniqueConstraint("version_id", "source_id", "url", name="uq_version_source_url"),
    )
    op.create_table(
        "scores",
        sa.Column("score_id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("event_versions.version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("dimensions_json", sa.Text(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("version_id", "config_version", name="uq_version_score_config"),
        sa.CheckConstraint("total >= 0 AND total <= 100", name="ck_score_total"),
        sa.CheckConstraint("config_version > 0", name="ck_score_config_positive"),
        sa.CheckConstraint("tier IN ('MUST_READ','IMPORTANT','EXTENDED')", name="ck_score_tier"),
    )

    for table_name in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER prevent_update_{table_name}
            BEFORE UPDATE ON {table_name}
            BEGIN
                SELECT RAISE(ABORT, '{table_name} is append-only');
            END
            """
        )


def downgrade() -> None:
    for table_name in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS prevent_update_{table_name}")
    for table_name in (
        "scores",
        "evidence",
        "raw_snapshots",
        "record_locks",
        "staged_commits",
        "active_scoring_config",
        "notes",
        "user_metadata",
        "event_versions",
        "projection_manifests",
        "recovery_audits",
        "deletion_audits",
        "scoring_configs",
        "events",
    ):
        op.drop_table(table_name)
