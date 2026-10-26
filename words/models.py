from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from games.models import WordProgress
    from users.models import User


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("user_id", "uuid", name="uq_user_word_uuid"),
        CheckConstraint("array_length(defs, 1) IS NOT NULL", name="ck_words_defs_not_empty"),
        CheckConstraint("gender IN ('masculine', 'feminine', 'both')", name="ck_words_gender"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    uuid: Mapped[str | None] = mapped_column(index=True)  # null => custom word
    name: Mapped[str] = mapped_column(index=True)
    language: Mapped[str] = mapped_column(index=True)
    fl: Mapped[str]  # part of speech
    stems: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    defs: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    audio_url: Mapped[str | None]
    transcription: Mapped[str | None]
    img_url: Mapped[str | None]
    img_desc: Mapped[str | None]  # caption of img_url
    gender: Mapped[str | None]  # "masculine" | "feminine" | "both" | None

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="words", lazy="raise")
    examples: Mapped[list["Example"]] = relationship(
        back_populates="word", cascade="all, delete-orphan", lazy="raise"
    )
    progress: Mapped[list["WordProgress"]] = relationship(
        back_populates="word", cascade="all, delete-orphan", lazy="raise"
    )


class Example(Base):
    __tablename__ = "word_examples"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    text: Mapped[str]
    translation: Mapped[str | None]

    word: Mapped["Word"] = relationship(back_populates="examples", lazy="raise")
