# words/service.py
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from words.models import Word, Example
from words.schemas import WordCreate


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