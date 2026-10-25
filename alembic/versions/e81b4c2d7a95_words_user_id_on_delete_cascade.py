"""words.user_id on delete cascade

Deleting a user now deletes their words, and through the existing cascades
their examples, progress and review logs. Before, the foreign key blocked
deleting a user who had any words.

Revision ID: e81b4c2d7a95
Revises: c3a7e5d91f20
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e81b4c2d7a95'
down_revision: Union[str, Sequence[str], None] = 'c3a7e5d91f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('words_user_id_fkey', 'words', type_='foreignkey')
    op.create_foreign_key(
        'words_user_id_fkey', 'words', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('words_user_id_fkey', 'words', type_='foreignkey')
    op.create_foreign_key('words_user_id_fkey', 'words', 'users', ['user_id'], ['id'])
