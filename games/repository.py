"""Queries on the games tables. Never commits; callers own the transaction."""
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from games.models import Game, GameLanguage, WordProgress


async def get_games_for_language(db: AsyncSession, language: str) -> list[Game]:
    """Games marked for all languages or linked to `language`, by `order_num`."""
    games = await db.scalars(
        select(Game)
        .where(
            or_(
                Game.all_languages.is_(True),
                Game.id.in_(
                    select(GameLanguage.game_id).where(GameLanguage.language == language)
                ),
            )
        )
        .order_by(Game.order_num)
    )
    return list(games.all())


async def get_review_dates(
    db: AsyncSession, game_type: str, word_ids: list[int]
) -> dict[int, tuple[datetime, datetime | None]]:
    """`(next_review_date, last_reviewed_at)` per word id, for words with progress in this game type."""
    if not word_ids:
        return {}
    # One bound parameter per id; fine for a personal vocabulary, but
    # Postgres caps a statement at 65535 parameters.
    rows = await db.execute(
        select(
            WordProgress.word_id,
            WordProgress.next_review_date,
            WordProgress.last_reviewed_at,
        ).where(
            WordProgress.game_type == game_type,
            WordProgress.word_id.in_(word_ids),
        )
    )
    return {row.word_id: (row.next_review_date, row.last_reviewed_at) for row in rows}


async def get_word_progress(db: AsyncSession, word_id: int, game_type: str) -> WordProgress | None:
    return await db.scalar(
        select(WordProgress).where(
            WordProgress.word_id == word_id,
            WordProgress.game_type == game_type,
        )
    )
