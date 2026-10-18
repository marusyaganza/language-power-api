"""Queries on the words tables. Never commits; callers own the transaction."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from words.models import Word
from words.schemas import SortOrder, VocabularySortBy

# Order used for each sort field when the caller does not choose one.
_DEFAULT_ORDER = {
    VocabularySortBy.name: SortOrder.asc,
    VocabularySortBy.created_at: SortOrder.desc,
}


async def get_saved_uuids(db: AsyncSession, user_id: int, uuids: list[str]) -> set[str]:
    if not uuids:
        return set()
    rows = await db.scalars(
        select(Word.uuid).where(Word.user_id == user_id, Word.uuid.in_(uuids))
    )
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
    items = await db.scalars(
        stmt.options(selectinload(Word.examples))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(items.all()), total
