# ruff: noqa: E501
"""Make Phase 5 rescoring appendable and archive formalization recoverable.

Revision ID: 0007_phase5_regression_fixes
Revises: 0006_phase5_intelligence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase5_regression_fixes"
down_revision: str | None = "0006_phase5_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REFLECTED_NAMES = {
    "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s",
}


def _create_append_only_triggers(table_name: str) -> None:
    op.execute(
        f"CREATE TRIGGER prevent_{table_name}_update BEFORE UPDATE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
    )
    op.execute(
        f"CREATE TRIGGER prevent_{table_name}_delete BEFORE DELETE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
    )


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prevent_candidate_scores_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_candidate_scores_delete")
    with op.batch_alter_table("candidate_scores", naming_convention=_REFLECTED_NAMES) as batch_op:
        batch_op.drop_constraint(
            "uq_candidate_scores_aggregate_version_id_config_version", type_="unique"
        )
        batch_op.add_column(
            sa.Column("score_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_unique_constraint(
            "uq_candidate_score_revision",
            ["aggregate_version_id", "config_version", "score_revision"],
        )
        batch_op.create_check_constraint("ck_candidate_score_revision", "score_revision > 0")
    with op.batch_alter_table("candidate_scores") as batch_op:
        batch_op.alter_column("score_revision", server_default=None)
    _create_append_only_triggers("candidate_scores")

    op.add_column(
        "staged_commits", sa.Column("formalization_selection_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "staged_commits",
        sa.Column("formalization_aggregate_version_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "staged_commits", sa.Column("formalization_archived_at", sa.String(40), nullable=True)
    )


def downgrade() -> None:
    # Downgrade is already guarded by explicit data-loss consent. Remove only
    # revision-dependent rows that cannot fit the Phase 5 v1 uniqueness model.
    for table_name in ("formalization_links", "daily_selections", "quality_feedback"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_update")
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_delete")
    op.execute("DROP TRIGGER IF EXISTS prevent_candidate_scores_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_candidate_scores_delete")
    op.execute(
        "DELETE FROM formalization_links WHERE selection_id IN "
        "(SELECT selection_id FROM daily_selections WHERE score_id IN "
        "(SELECT score_id FROM candidate_scores WHERE score_revision > 1))"
    )
    op.execute(
        "DELETE FROM daily_selections WHERE score_id IN "
        "(SELECT score_id FROM candidate_scores WHERE score_revision > 1)"
    )
    op.execute(
        "DELETE FROM quality_feedback WHERE score_id IN "
        "(SELECT score_id FROM candidate_scores WHERE score_revision > 1)"
    )
    op.execute("DELETE FROM candidate_scores WHERE score_revision > 1")

    with op.batch_alter_table("candidate_scores") as batch_op:
        batch_op.drop_constraint("uq_candidate_score_revision", type_="unique")
        batch_op.drop_constraint("ck_candidate_score_revision", type_="check")
        batch_op.drop_column("score_revision")
        batch_op.create_unique_constraint(
            "uq_candidate_score_config", ["aggregate_version_id", "config_version"]
        )
    _create_append_only_triggers("candidate_scores")
    for table_name in ("quality_feedback", "daily_selections", "formalization_links"):
        _create_append_only_triggers(table_name)

    with op.batch_alter_table("staged_commits") as batch_op:
        batch_op.drop_column("formalization_archived_at")
        batch_op.drop_column("formalization_aggregate_version_id")
        batch_op.drop_column("formalization_selection_id")
