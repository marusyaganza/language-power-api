"""add unit and key to krdict entries

Revision ID: 957296609d54
Revises: 44790501fc59
Create Date: 2026-11-03 12:48:38.875405

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "957296609d54"
down_revision: str | Sequence[str] | None = "44790501fc59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As in dictionary/ko/models.py when this migration was written.
UNITS = ("단어", "구", "관용구", "속담", "문법‧표현")


def upgrade() -> None:
    """Upgrade schema.

    The Korean dictionary now keeps phrases, idioms, proverbs and grammar
    patterns too, so each entry says which kind it is (`unit`). Idioms and
    proverbs share the dictionary id of the word they're built on, so the
    primary key moves from `id` to a text `key` (dictionary/ko/models.py).
    Rows imported before were all single words: `unit` 단어 and `key` = id.
    """
    op.add_column("krdict_entries", sa.Column("unit", sa.String(), server_default="단어", nullable=False))
    op.alter_column("krdict_entries", "unit", server_default=None)
    op.create_check_constraint(
        "ck_krdict_entries_unit", "krdict_entries", "unit IN ({})".format(", ".join(f"'{u}'" for u in UNITS))
    )

    op.add_column("krdict_entries", sa.Column("key", sa.String(), nullable=True))
    op.execute("UPDATE krdict_entries SET key = id::text")
    op.alter_column("krdict_entries", "key", nullable=False)
    op.drop_constraint("krdict_entries_pkey", "krdict_entries", type_="primary")
    op.create_primary_key("krdict_entries_pkey", "krdict_entries", ["key"])
    op.create_index(op.f("ix_krdict_entries_id"), "krdict_entries", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Only single words have unique ids, so everything else is deleted first;
    the next import with an older version of the script would skip it anyway.
    """
    op.execute("DELETE FROM krdict_entries WHERE unit <> '단어'")
    op.drop_index(op.f("ix_krdict_entries_id"), table_name="krdict_entries")
    op.drop_constraint("krdict_entries_pkey", "krdict_entries", type_="primary")
    op.create_primary_key("krdict_entries_pkey", "krdict_entries", ["id"])
    op.drop_column("krdict_entries", "key")
    op.drop_constraint("ck_krdict_entries_unit", "krdict_entries", type_="check")
    op.drop_column("krdict_entries", "unit")
