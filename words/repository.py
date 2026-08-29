# words/repository.py
from sqlalchemy.orm import Session
from words.models import Word


def get_saved_uuids(db: Session, user_id: int, uuids: list[str]) -> set[str]:
    if not uuids:
        return set()
    rows = (
        db.query(Word.uuid)
        .filter(Word.user_id == user_id, Word.uuid.in_(uuids))
        .all()
    )
    return {r.uuid for r in rows}