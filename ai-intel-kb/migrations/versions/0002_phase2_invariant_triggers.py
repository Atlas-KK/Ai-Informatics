"""Separate immutable configuration content from confirmed active-state changes.

Revision ID: 0002_phase2_invariant_triggers
Revises: 0001_phase2_archive
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_phase2_invariant_triggers"
down_revision: str | None = "0001_phase2_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TRIGGER prevent_update_scoring_configs")
    op.execute(
        """
        CREATE TRIGGER prevent_scoring_config_content_update
        BEFORE UPDATE OF config_version, weights_json, source_overrides_json, created_at
        ON scoring_configs
        BEGIN
            SELECT RAISE(ABORT, 'scoring configuration content is append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_formal_event_field_update
        BEFORE UPDATE OF canonical_title, primary_topic, created_at ON events
        WHEN OLD.current_version IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'formal event fields are read-only');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prevent_formal_event_field_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_scoring_config_content_update")
    op.execute(
        """
        CREATE TRIGGER prevent_update_scoring_configs
        BEFORE UPDATE ON scoring_configs
        BEGIN
            SELECT RAISE(ABORT, 'scoring_configs is append-only');
        END
        """
    )
