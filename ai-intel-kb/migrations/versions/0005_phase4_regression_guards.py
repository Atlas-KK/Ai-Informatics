"""Guard Phase 4 aggregate identity and current-version transitions.

Revision ID: 0005_phase4_regression_guards
Revises: 0004_phase4_event_aggregation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_phase4_regression_guards"
down_revision: str | None = "0004_phase4_event_aggregation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER prevent_event_aggregate_stable_key_update
        BEFORE UPDATE OF stable_key ON event_aggregates
        WHEN NEW.stable_key != OLD.stable_key
        BEGIN
            SELECT RAISE(ABORT, 'event aggregate stable key is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER validate_event_aggregate_version_update
        BEFORE UPDATE OF current_version ON event_aggregates
        WHEN NEW.current_version != OLD.current_version
        BEGIN
            SELECT CASE
                WHEN NEW.current_version != OLD.current_version + 1
                THEN RAISE(ABORT, 'invalid aggregate current-version transition')
            END;
            SELECT CASE
                WHEN NOT EXISTS (
                    SELECT 1 FROM aggregate_versions
                    WHERE event_id = OLD.event_id AND version_no = NEW.current_version
                )
                THEN RAISE(ABORT, 'aggregate current version does not exist')
            END;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER validate_event_aggregate_title_update
        BEFORE UPDATE OF canonical_title, normalized_title ON event_aggregates
        WHEN (
            NEW.canonical_title != OLD.canonical_title
            OR NEW.normalized_title != OLD.normalized_title
        ) AND NEW.current_version = OLD.current_version
        BEGIN
            SELECT RAISE(ABORT, 'aggregate title changes require a new version');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS validate_event_aggregate_title_update")
    op.execute("DROP TRIGGER IF EXISTS validate_event_aggregate_version_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_event_aggregate_stable_key_update")
