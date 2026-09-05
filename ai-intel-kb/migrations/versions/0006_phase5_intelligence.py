# ruff: noqa: E501
"""Add Phase 5 AI processing, scoring, selection and calibration records.

Revision ID: 0006_phase5_intelligence
Revises: 0005_phase4_regression_guards
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase5_intelligence"
down_revision: str | None = "0005_phase4_regression_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_TABLES = (
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
)


def upgrade() -> None:
    op.create_table(
        "ai_processing_results",
        sa.Column("result_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_language", sa.String(2), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("zh_translation", sa.Text()),
        sa.Column("zh_summary", sa.Text(), nullable=False),
        sa.Column("key_conclusions_json", sa.Text(), nullable=False),
        sa.Column("pm_value", sa.Text(), nullable=False),
        sa.Column("primary_topic", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("dimension_scores_json", sa.Text(), nullable=False),
        sa.Column("dimension_rationales_json", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("source_language IN ('en','zh')"),
        sa.CheckConstraint("origin IN ('COLLECTOR','MANUAL_INBOX','EXTENDED_SEARCH')"),
        sa.CheckConstraint(
            "primary_topic IN ('大模型与智能体','AI 产品形态与行业应用','AI 产品实战','AI 工程安全与可靠性')"
        ),
    )
    op.create_table(
        "ai_processing_failures",
        sa.Column("failure_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("stage IN ('FILTER','PROCESSING','SCORING','TOPIC_IDEA')"),
    )
    op.create_table(
        "candidate_scores",
        sa.Column("score_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "processing_result_id",
            sa.String(36),
            sa.ForeignKey("ai_processing_results.result_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "config_version",
            sa.Integer(),
            sa.ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dimensions_json", sa.Text(), nullable=False),
        sa.Column("rationales_json", sa.Text(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("aggregate_version_id", "config_version"),
        sa.CheckConstraint("total >= 0 AND total <= 100"),
    )
    op.create_table(
        "daily_selection_runs",
        sa.Column("selection_run_id", sa.String(36), primary_key=True),
        sa.Column("report_date", sa.String(10), nullable=False),
        sa.Column(
            "config_version",
            sa.Integer(),
            sa.ForeignKey("scoring_configs.config_version", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("max_items", sa.Integer(), nullable=False),
        sa.Column("qualified_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("threshold >= 0 AND threshold <= 100"),
        sa.CheckConstraint("max_items >= 1 AND max_items <= 50"),
        sa.CheckConstraint("qualified_count >= 0"),
    )
    op.create_table(
        "daily_selections",
        sa.Column("selection_id", sa.String(36), primary_key=True),
        sa.Column(
            "selection_run_id",
            sa.String(36),
            sa.ForeignKey("daily_selection_runs.selection_run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "score_id",
            sa.String(36),
            sa.ForeignKey("candidate_scores.score_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("selection_run_id", "event_id"),
        sa.UniqueConstraint("selection_run_id", "rank"),
        sa.CheckConstraint("rank >= 1 AND rank <= 50"),
        sa.CheckConstraint("tier IN ('MUST_READ','IMPORTANT','EXTENDED')"),
    )
    op.create_table(
        "formalization_links",
        sa.Column("link_id", sa.String(36), primary_key=True),
        sa.Column(
            "selection_id",
            sa.String(36),
            sa.ForeignKey("daily_selections.selection_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "formal_event_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column("formal_version_no", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("formal_event_id", "formal_version_no"),
        sa.CheckConstraint("formal_version_no > 0"),
    )
    op.create_table(
        "quality_feedback",
        sa.Column("feedback_id", sa.String(36), primary_key=True),
        sa.Column(
            "score_id",
            sa.String(36),
            sa.ForeignKey("candidate_scores.score_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_dimension", sa.String(30), nullable=False),
        sa.Column("content_features_json", sa.Text(), nullable=False),
        sa.Column("original_score", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("length(trim(reason)) > 0"),
        sa.CheckConstraint("original_score >= 0 AND original_score <= 100"),
        sa.CheckConstraint("outcome IN ('REMOVED','KEPT')"),
    )
    op.create_table(
        "calibration_proposals",
        sa.Column("proposal_id", sa.String(36), primary_key=True),
        sa.Column(
            "base_config_version",
            sa.Integer(),
            sa.ForeignKey("scoring_configs.config_version"),
            nullable=False,
        ),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("uncertainty", sa.String(20), nullable=False),
        sa.Column("affected_dimensions_json", sa.Text(), nullable=False),
        sa.Column("suggested_weights_json", sa.Text(), nullable=False),
        sa.Column("suggested_source_overrides_json", sa.Text(), nullable=False),
        sa.Column("estimated_impact_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("sample_count > 0"),
        sa.CheckConstraint("uncertainty IN ('LOW','MEDIUM','HIGH')"),
    )
    op.create_table(
        "calibration_decisions",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("calibration_proposals.proposal_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column(
            "new_config_version", sa.Integer(), sa.ForeignKey("scoring_configs.config_version")
        ),
        sa.Column("decided_at", sa.String(40), nullable=False),
        sa.CheckConstraint("decision IN ('CONFIRMED','REJECTED')"),
    )
    op.create_table(
        "scoring_config_audits",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("old_config_version", sa.Integer()),
        sa.Column(
            "new_config_version",
            sa.Integer(),
            sa.ForeignKey("scoring_configs.config_version"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("proposal_id", sa.String(36)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("action IN ('INITIALIZE','CONFIRM','ROLLBACK')"),
    )
    op.create_table(
        "topic_ideas",
        sa.Column("idea_id", sa.String(36), primary_key=True),
        sa.Column(
            "aggregate_version_id",
            sa.String(36),
            sa.ForeignKey("aggregate_versions.aggregate_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("outline_json", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("support_evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("aggregate_version_id", "trigger"),
        sa.CheckConstraint("trigger IN ('AUTO','MANUAL')"),
    )
    for table_name in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER prevent_{table_name}_update BEFORE UPDATE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
        )
        op.execute(
            f"CREATE TRIGGER prevent_{table_name}_delete BEFORE DELETE ON {table_name} BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"
        )


def downgrade() -> None:
    for table_name in reversed(APPEND_ONLY_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_delete")
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_update")
        op.drop_table(table_name)
