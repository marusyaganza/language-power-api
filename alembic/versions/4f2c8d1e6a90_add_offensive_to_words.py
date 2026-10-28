"""add offensive to words

Revision ID: 4f2c8d1e6a90
Revises: e81b4c2d7a95
Create Date: 2026-10-27 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2c8d1e6a90"
down_revision: str | Sequence[str] | None = "e81b4c2d7a95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Words saved before this migration are marked not offensive; the label is
    not looked up again for them.
    """
    op.add_column("words", sa.Column("offensive", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("words", "offensive")
