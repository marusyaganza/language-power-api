# words/service.py
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from fastapi import HTTPException, status
from math import ceil
from words.repository import get_vocabulary
from words.models import Word, Example
from words.schemas import WordCreate, VocabularyPage, VocabularySortBy, WordOut, WordUpdate


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
        gender=payload.gender,
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
    language: str,
    query: str | None,
    page: int,
    sort_by: VocabularySortBy,
) -> VocabularyPage:
    page_size = 10
    items, total = get_vocabulary(
        db, user_id, language=language, query=query, page=page, page_size=page_size, sort_by=sort_by
    )
    return VocabularyPage(
        items=[WordOut.model_validate(w) for w in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
    )

def delete_word(db: Session, user_id: int, word_id: int) -> None:
    word = (
        db.query(Word)
        .filter(Word.id == word_id, Word.user_id == user_id)
        .first()
    )
    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )
    db.delete(word)
    db.commit()

def update_word(db: Session, user_id: int, word_id: int, payload: WordUpdate) -> Word:
    word = (
        db.query(Word)
        .filter(Word.id == word_id, Word.user_id == user_id)
        .first()
    )
    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )

    if payload.defs is not None:
        word.defs = payload.defs
    if payload.audio_url is not None:
        word.audio_url = payload.audio_url
    if payload.img_url is not None:
        word.img_url = payload.img_url

    if payload.examples is not None:
        word.examples = [
            Example(text=e.text, translation=e.translation)
            for e in payload.examples
        ]
        # relationship reassignment + cascade="all, delete-orphan" on Word.examples
        # (defined in models.py) handles deleting the old rows automatically

    db.commit()
    db.refresh(word)
    return word

def count_saved_words(
    session,
    user_id: int,
    language: str,
    *,
    requires_audio: bool = False,
    requires_image: bool = False,
    requires_gender: bool = False,
) -> int:
    query = select(func.count()).select_from(Word).where(
        Word.user_id == user_id,
        Word.language == language,
    )
    if requires_audio:
        query = query.where(Word.audio_url.is_not(None))
    if requires_image:
        query = query.where(Word.img_url.is_not(None))
    if requires_gender:
        query = query.where(Word.gender.is_not(None))

    return session.scalar(query) or 0

