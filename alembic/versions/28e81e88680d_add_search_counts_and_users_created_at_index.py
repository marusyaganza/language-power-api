"""add search counts and an index on users.created_at

Revision ID: 28e81e88680d
Revises: 4f2c8d1e6a90
Create Date: 2026-10-28 10:38:01.498858

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28e81e88680d"
down_revision: str | Sequence[str] | None = "4f2c8d1e6a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    The tables count dictionary searches for the demo's limits (settings
    `searches_per_language`, `daily_searches_per_language`); the index serves
    the daily signup count and deleting expired accounts.
    """
    op.create_table(
        "daily_search_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", "language"),
    )
    op.create_table(
        "search_counts",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "language"),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_table("search_counts")
    op.drop_table("daily_search_counts")
