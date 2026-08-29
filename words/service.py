# words/service.py
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from math import ceil
from words.repository import get_vocabulary
from words.models import Word, Example
from words.schemas import WordCreate, VocabularyPage, VocabularySortBy, WordOut


def save_word(db: Session, user_id: int, payload: WordCreate) -> Word:
    word = Word(
        user_id=user_id,
        uuid=payload.uuid,
        name=payload.name,
        language=payload.language,
        stems=payload.stems,
        defs=payload.defs,
        fl=payload.fl,
        audio_url=payload.audio_url,
        transcription=payload.transcription,
        img_url=payload.img_url,
        examples=[
            Example(text=e.text, translation=e.translation)
            for e in payload.examples
        ],
    )
    db.add(word)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Word already saved",
        )
    db.refresh(word)
    return word

def get_vocabulary_page(
    db: Session,
    user_id: int,
    *,
    query: str | None,
    page: int,
    sort_by: VocabularySortBy,
) -> VocabularyPage:
    page_size = 5
    items, total = get_vocabulary(
        db, user_id, query=query, page=page, page_size=page_size, sort_by=sort_by
    )
    return VocabularyPage(
        items=[WordOut.model_validate(w) for w in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )