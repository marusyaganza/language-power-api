# words/repository.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from math import ceil
from words.models import Word
from words.schemas import VocabularySortBy

def get_saved_uuids(db: Session, user_id: int, uuids: list[str]) -> set[str]:
    if not uuids:
        return set()
    rows = (
        db.query(Word.uuid)
        .filter(Word.user_id == user_id, Word.uuid.in_(uuids))
        .all()
    )
    return {r.uuid for r in rows}

def get_vocabulary(
    db: Session,
    user_id: int,
    *,
    language: str,
    query: str | None = None,
    page: int = 1,
    page_size: int = 5,
    sort_by: VocabularySortBy = VocabularySortBy.created_at,
) -> tuple[list[Word], int]:
    q = db.query(Word).filter(Word.user_id == user_id, Word.language == language)

    if query:
        q = q.filter(Word.name.ilike(f"%{query}%"))

    total = q.with_entities(func.count(Word.id)).scalar()

    if sort_by == VocabularySortBy.name:
        q = q.order_by(Word.name.asc())
    else:
        q = q.order_by(Word.created_at.desc())

    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return items, total