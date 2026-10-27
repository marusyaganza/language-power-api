"""remove duplicate word definitions

Revision ID: a585950f8bff
Revises: 8188cd69cc46
Create Date: 2026-10-17 19:34:53.644517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a585950f8bff'
down_revision: Union[str, Sequence[str], None] = '8188cd69cc46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Strip definitions and drop repeats, keeping the first of each.

    Same rule as `dictionary.entry.unique_definitions`: definitions that differ only
    in case or spacing are repeats. Only rows that change are updated.
    """
    op.execute(
        """
        UPDATE words AS w
        SET defs = u.defs
        FROM (
            SELECT id, array_agg(def ORDER BY first_pos)::varchar[] AS defs
            FROM (
                SELECT
                    w.id,
                    min(d.pos) AS first_pos,
                    (array_agg(btrim(d.def) ORDER BY d.pos))[1] AS def
                FROM words AS w
                CROSS JOIN LATERAL unnest(w.defs) WITH ORDINALITY AS d(def, pos)
                GROUP BY w.id, lower(regexp_replace(btrim(d.def), '\\s+', ' ', 'g'))
            ) AS firsts
            GROUP BY id
        ) AS u
        WHERE u.id = w.id AND u.defs <> w.defs
        """
    )


def downgrade() -> None:
    """Nothing to undo: the removed definitions were repeats."""
