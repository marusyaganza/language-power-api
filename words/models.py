from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("user_id", "uuid", name="uq_user_word_uuid"),
        CheckConstraint("array_length(defs, 1) IS NOT NULL", name="ck_words_defs_not_empty"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    uuid = Column(String, nullable=True, index=True)  # null => custom word
    name = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False, index=True)
    fl = Column(String, nullable=False)  # part of speech
    stems = Column(ARRAY(String), nullable=False, server_default="{}")
    defs = Column(ARRAY(String), nullable=False, server_default="{}")
    audio_url = Column(String, nullable=True)
    transcription = Column(String, nullable=True)
    img_url = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="words", lazy="raise")
    examples = relationship("Example", back_populates="word", cascade="all, delete-orphan", lazy="raise")
    progress = relationship("WordProgress", back_populates="word", cascade="all, delete-orphan", lazy="raise")

    gender: Mapped[str | None] = mapped_column(nullable=True)  # "masculine" | "feminine" | None

class Example(Base):
    __tablename__ = "word_examples"

    id = Column(Integer, primary_key=True, index=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(String, nullable=False)
    translation = Column(String, nullable=True)

    word = relationship("Word", back_populates="examples", lazy="raise")