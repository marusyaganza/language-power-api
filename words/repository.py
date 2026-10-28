"""Queries on the words tables. Never commits; callers own the transaction."""

from datetime import date

from sqlalchemy import Row, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from words.models import DailySearchCount, SearchCount, Word
from words.schemas import SortOrder, VocabularySortBy

# Order used for each sort field when the caller does not choose one.
_DEFAULT_ORDER = {
    VocabularySortBy.name: SortOrder.asc,
    VocabularySortBy.created_at: SortOrder.desc,
}


async def get_saved_uuids(db: AsyncSession, user_id: int, uuids: list[str]) -> set[str]:
    if not uuids:
        return set()
    rows = await db.scalars(select(Word.uuid).where(Word.user_id == user_id, Word.uuid.in_(uuids)))
    return set(rows.all())


async def get_vocabulary(
    db: AsyncSession,
    user_id: int,
    *,
    language: str,
    query: str | None = None,
    page: int = 1,
    page_size: int = 5,
    sort_by: VocabularySortBy = VocabularySortBy.created_at,
    sort_order: SortOrder | None = None,
) -> tuple[list[Word], int]:
    stmt = select(Word).where(Word.user_id == user_id, Word.language == language)

    if query:
        stmt = stmt.where(Word.name.ilike(f"%{query}%"))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = Word.name if sort_by == VocabularySortBy.name else Word.created_at
    order = sort_order or _DEFAULT_ORDER[sort_by]
    stmt = stmt.order_by(column.asc() if order == SortOrder.asc else column.desc())

    # Callers serialize `examples`, and an async session cannot lazy-load them.
    items = await db.scalars(stmt.options(selectinload(Word.examples)).offset((page - 1) * page_size).limit(page_size))
    return list(items.all()), total


async def get_word(db: AsyncSession, user_id: int, word_id: int) -> Word | None:
    """One of the user's words with its examples, or None (also if it belongs to another user)."""
    return await db.scalar(
        select(Word).options(selectinload(Word.examples)).where(Word.id == word_id, Word.user_id == user_id)
    )


async def get_word_ids(
    db: AsyncSession,
    user_id: int,
    language: str,
    *,
    requires_audio: bool,
    requires_image: bool,
    requires_gender: bool,
) -> list[int]:
    stmt = select(Word.id).where(Word.user_id == user_id, Word.language == language)
    if requires_audio:
        stmt = stmt.where(Word.audio_url.is_not(None))
    if requires_image:
        stmt = stmt.where(Word.img_url.is_not(None))
    if requires_gender:
        stmt = stmt.where(Word.gender.is_not(None))
    result = await db.scalars(stmt)
    return list(result.all())


async def get_word_summary_rows(
    db: AsyncSession, user_id: int, word_ids: list[int]
) -> list[Row[tuple[int, str, list[str], list[str]]]]:
    """(id, name, stems, defs) of the user's words with these ids."""
    if not word_ids:
        return []
    rows = await db.execute(
        select(Word.id, Word.name, Word.stems, Word.defs).where(Word.user_id == user_id, Word.id.in_(word_ids))
    )
    return list(rows.all())


async def get_words_by_ids(db: AsyncSession, user_id: int, word_ids: list[int]) -> list[Word]:
    """The user's words with these ids, with their examples."""
    if not word_ids:
        return []
    result = await db.scalars(
        select(Word).options(selectinload(Word.examples)).where(Word.user_id == user_id, Word.id.in_(word_ids))
    )
    return list(result.all())


async def count_words(db: AsyncSession, user_id: int) -> int:
    """How many words the user has saved, in all languages."""
    return await db.scalar(select(func.count()).select_from(Word).where(Word.user_id == user_id)) or 0


async def add_search(db: AsyncSession, user_id: int, language: str, *, limit: int) -> int | None:
    """Count one search by the user in `language`, unless `limit` is reached.

    Returns the new count, or None if the count was already `limit` (then
    nothing changes). One statement, so two requests at once can't both pass.
    """
    stmt = (
        insert(SearchCount)
        .values(user_id=user_id, language=language, count=1)
        .on_conflict_do_update(
            index_elements=[SearchCount.user_id, SearchCount.language],
            set_={"count": SearchCount.count + 1},
            where=SearchCount.count < limit,
        )
        .returning(SearchCount.count)
    )
    return await db.scalar(stmt)


async def add_daily_search(db: AsyncSession, day: date, language: str, *, limit: int) -> int | None:
    """Count one search in `language` on `day`, unless `limit` is reached; like `add_search`."""
    stmt = (
        insert(DailySearchCount)
        .values(day=day, language=language, count=1)
        .on_conflict_do_update(
            index_elements=[DailySearchCount.day, DailySearchCount.language],
            set_={"count": DailySearchCount.count + 1},
            where=DailySearchCount.count < limit,
        )
        .returning(DailySearchCount.count)
    )
    return await db.scalar(stmt)


async def get_search_counts(db: AsyncSession, user_id: int) -> dict[str, int]:
    """The user's search count per language; languages never searched are missing."""
    rows = await db.execute(select(SearchCount.language, SearchCount.count).where(SearchCount.user_id == user_id))
    return {row.language: row.count for row in rows}
