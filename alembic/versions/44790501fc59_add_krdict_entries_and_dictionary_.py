"""add krdict entries and dictionary imports

Revision ID: 44790501fc59
Revises: 28e81e88680d
Create Date: 2026-11-02 19:07:52.042384

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "44790501fc59"
down_revision: str | Sequence[str] | None = "28e81e88680d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    The Korean dictionary is imported data (dictionary/ko/models.py), filled
    by the import script, not by this migration. pg_trgm provides the
    similarity index for spelling suggestions. It is a trusted extension, so
    the database owner can create it (also on Neon).
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "dictionary_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("release", sa.String(), nullable=False),
        sa.Column("commit", sa.String(), nullable=True),
        sa.Column("file_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("entries", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "krdict_entries",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("word", sa.String(), nullable=False),
        sa.Column("homonym_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pos", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=True),
        sa.Column("pronunciation", sa.String(), nullable=True),
        sa.Column("forms", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("senses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("level IN ('초급', '중급', '고급')", name="ck_krdict_entries_level"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_krdict_entries_forms", "krdict_entries", ["forms"], unique=False, postgresql_using="gin")
    op.create_index(op.f("ix_krdict_entries_word"), "krdict_entries", ["word"], unique=False)
    op.create_index(
        "ix_krdict_entries_word_trgm",
        "krdict_entries",
        ["word"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"word": "gin_trgm_ops"},
    )


def downgrade() -> None:
    """Downgrade schema.

    pg_trgm stays installed: it may have existed before this migration (the
    upgrade only creates it if missing), and an unused extension does no harm.
    """
    op.drop_index(
        "ix_krdict_entries_word_trgm",
        table_name="krdict_entries",
        postgresql_using="gin",
        postgresql_ops={"word": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_krdict_entries_word"), table_name="krdict_entries")
    op.drop_index("ix_krdict_entries_forms", table_name="krdict_entries", postgresql_using="gin")
    op.drop_table("krdict_entries")
    op.drop_table("dictionary_imports")
