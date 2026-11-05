"""index korean headwords by letters for suggestions

Revision ID: 7e1e2a6cfad0
Revises: 957296609d54
Create Date: 2026-11-04 14:10:11.556537

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e1e2a6cfad0"
down_revision: str | Sequence[str] | None = "957296609d54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Spelling suggestions compare trigrams of letters, not syllables: a
    2-syllable Korean word has too few syllable trigrams for a one-letter typo
    to reach pg_trgm's 0.3 threshold (가게 vs 가개: 0.2; on letters 0.43).
    normalize(..., NFD) splits each syllable into its letters, and is
    immutable, so it can be indexed.
    """
    op.drop_index(
        "ix_krdict_entries_word_trgm",
        table_name="krdict_entries",
        postgresql_using="gin",
        postgresql_ops={"word": "gin_trgm_ops"},
    )
    op.execute(
        "CREATE INDEX ix_krdict_entries_word_nfd_trgm ON krdict_entries USING gin (normalize(word, NFD) gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_krdict_entries_word_nfd_trgm", table_name="krdict_entries")
    op.create_index(
        "ix_krdict_entries_word_trgm",
        "krdict_entries",
        ["word"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"word": "gin_trgm_ops"},
    )
