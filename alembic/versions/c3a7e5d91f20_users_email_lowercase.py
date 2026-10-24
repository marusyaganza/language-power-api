"""users email lowercase

Lowercases existing emails, then keeps them lowercase with a check constraint.
If two accounts differ only by case, the update violates the unique index and
the migration stops; merge or delete one of them first.

Revision ID: c3a7e5d91f20
Revises: deb9cb7acccf
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a7e5d91f20'
down_revision: Union[str, Sequence[str], None] = 'deb9cb7acccf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint('ck_users_email_lowercase', 'users', 'email = lower(email)')


def downgrade() -> None:
    """Downgrade schema."""
    # Emails stay lowercase; the original case is not kept.
    op.drop_constraint('ck_users_email_lowercase', 'users', type_='check')
