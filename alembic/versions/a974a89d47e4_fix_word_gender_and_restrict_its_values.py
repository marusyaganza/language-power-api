"""fix word gender and restrict its values

Revision ID: a974a89d47e4
Revises: a585950f8bff
Create Date: 2026-10-17 19:55:48.488191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a974a89d47e4'
down_revision: Union[str, Sequence[str], None] = 'a585950f8bff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same rule as dictionary.helpers.mw.extract_gender. Words whose part of
# speech names no gender keep a valid gender (custom words) and lose an
# invalid one, so the constraint below can be added.
_GENDER_FROM_FL = """
    CASE
        WHEN fl ILIKE '%masculine%' AND fl ILIKE '%feminine%' THEN 'both'
        WHEN fl ILIKE '%feminine%' THEN 'feminine'
        WHEN fl ILIKE '%masculine%' THEN 'masculine'
        WHEN gender IN ('masculine', 'feminine', 'both') THEN gender
    END
"""


def upgrade() -> None:
    """Re-derive gender ("masculine or feminine" nouns became "feminine") and restrict its values."""
    op.execute(
        f"UPDATE words SET gender = {_GENDER_FROM_FL} WHERE gender IS DISTINCT FROM {_GENDER_FROM_FL}"
    )
    op.create_check_constraint(
        "ck_words_gender", "words", "gender IN ('masculine', 'feminine', 'both')"
    )


def downgrade() -> None:
    """Drop the constraint; the corrected genders are kept."""
    op.drop_constraint("ck_words_gender", "words", type_="check")
