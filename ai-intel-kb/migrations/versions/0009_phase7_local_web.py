# ruff: noqa: E501
"""Add Phase 7 local web settings, full-text index and transient search state.

Revision ID: 0009_phase7_local_web
Revises: 0008_phase6_pipeline_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_phase7_local_web"
down_revision: str | None = "0008_phase6_pipeline_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings_table = op.create_table(
        "ui_settings",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("schedule_time", sa.String(5), nullable=False),
        sa.Column("selection_threshold", sa.Float(), nullable=False),
        sa.Column("tier_caps_json", sa.Text(), nullable=False),
        sa.Column("topic_order_json", sa.Text(), nullable=False),
        sa.Column("default_sort", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("singleton_id = 1"),
        sa.CheckConstraint("selection_threshold >= 0 AND selection_threshold <= 100"),
        sa.CheckConstraint("default_sort IN ('PUBLISHED_DESC','SCORE_DESC')"),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "singleton_id": 1,
                "schedule_time": "08:30",
                "selection_threshold": 70,
                "tier_caps_json": '{"MUST_READ":10,"IMPORTANT":20,"EXTENDED":20}',
                "topic_order_json": (
                    '["大模型与智能体","AI 产品形态与行业应用","AI 产品实战","AI 工程安全与可靠性"]'
                ),
                "default_sort": "PUBLISHED_DESC",
                "updated_at": "2026-09-04T00:00:00+00:00",
            }
        ],
    )
    op.create_table(
        "archive_search_documents",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source_updated_at", sa.String(40), nullable=False),
    )
    op.execute(
        "CREATE VIRTUAL TABLE archive_search_fts USING fts5("
        "event_id UNINDEXED, title, summary, content, sources, tags, note, "
        "content='archive_search_documents', content_rowid='rowid', tokenize='unicode61')"
    )
    op.execute(
        "CREATE TRIGGER archive_search_ai AFTER INSERT ON archive_search_documents BEGIN "
        "INSERT INTO archive_search_fts(rowid,event_id,title,summary,content,sources,tags,note) "
        "VALUES(new.rowid,new.event_id,new.title,new.summary,new.content,new.sources,new.tags,new.note); END"
    )
    op.execute(
        "CREATE TRIGGER archive_search_ad AFTER DELETE ON archive_search_documents BEGIN "
        "INSERT INTO archive_search_fts(archive_search_fts,rowid,event_id,title,summary,content,sources,tags,note) "
        "VALUES('delete',old.rowid,old.event_id,old.title,old.summary,old.content,old.sources,old.tags,old.note); END"
    )
    op.execute(
        "CREATE TRIGGER archive_search_au AFTER UPDATE ON archive_search_documents BEGIN "
        "INSERT INTO archive_search_fts(archive_search_fts,rowid,event_id,title,summary,content,sources,tags,note) "
        "VALUES('delete',old.rowid,old.event_id,old.title,old.summary,old.content,old.sources,old.tags,old.note); "
        "INSERT INTO archive_search_fts(rowid,event_id,title,summary,content,sources,tags,note) "
        "VALUES(new.rowid,new.event_id,new.title,new.summary,new.content,new.sources,new.tags,new.note); END"
    )
    op.create_table(
        "extension_search_runs",
        sa.Column("search_run_id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("status IN ('SUCCEEDED','FAILED','UNAVAILABLE')"),
    )
    op.create_table(
        "extension_search_results",
        sa.Column("result_id", sa.String(36), primary_key=True),
        sa.Column(
            "search_run_id",
            sa.String(36),
            sa.ForeignKey("extension_search_runs.search_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("formal_event_id", sa.String(36)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("search_run_id", "url"),
        sa.CheckConstraint("score >= 0 AND score <= 100"),
    )


def downgrade() -> None:
    op.drop_table("extension_search_results")
    op.drop_table("extension_search_runs")
    for trigger in ("archive_search_au", "archive_search_ad", "archive_search_ai"):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS archive_search_fts")
    op.drop_table("archive_search_documents")
    op.drop_table("ui_settings")
