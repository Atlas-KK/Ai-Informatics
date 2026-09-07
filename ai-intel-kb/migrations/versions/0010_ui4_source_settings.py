"""Add persisted GitHub discovery settings for UI-4.

Revision ID: 0010_ui4_source_settings
Revises: 0009_phase7_local_web
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_ui4_source_settings"
down_revision: str | None = "0009_phase7_local_web"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings_table = op.create_table(
        "github_discovery_settings",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("daily_trending", sa.Boolean(), nullable=False),
        sa.Column("weekly_trending", sa.Boolean(), nullable=False),
        sa.Column("seven_day_star_growth", sa.Boolean(), nullable=False),
        sa.Column("ai_relevance", sa.Boolean(), nullable=False),
        sa.Column("whitelist_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("singleton_id = 1"),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "singleton_id": 1,
                "daily_trending": True,
                "weekly_trending": True,
                "seven_day_star_growth": True,
                "ai_relevance": True,
                "whitelist_json": "[]",
                "updated_at": "2026-09-06T00:00:00+00:00",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("github_discovery_settings")
