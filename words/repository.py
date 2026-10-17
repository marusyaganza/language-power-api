"""Queries on the words tables. Never commits; callers own the transaction."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from words.models import Word
from words.schemas import VocabularySortBy


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
) -> tuple[list[Word], int]:
    stmt = select(Word).where(Word.user_id == user_id, Word.language == language)

    if query:
        stmt = stmt.where(Word.name.ilike(f"%{query}%"))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sort_by == VocabularySortBy.name:
        stmt = stmt.order_by(Word.name.asc())
    else:
        stmt = stmt.order_by(Word.created_at.desc())

    # Callers serialize `examples`, and an async session cannot lazy-load them.
    items = await db.scalars(
        stmt.options(selectinload(Word.examples))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(items.all()), total
