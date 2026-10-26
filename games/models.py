import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from words.models import Word


class GameType(str, enum.Enum):
    AUDIO = "audio"
    SELECT_DEF = "select_def"
    SELECT_WORD = "select_word"
    TYPE_WORD = "type_word"
    IMAGE = "image"
    GENDER = "gender"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    title: Mapped[str]
    description: Mapped[str]
    game_type: Mapped[GameType]
    order_num: Mapped[int] = mapped_column(default=0)
    all_languages: Mapped[bool] = mapped_column(default=False)
    default_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    languages: Mapped[list["GameLanguage"]] = relationship(cascade="all, delete-orphan", lazy="raise")


class GameLanguage(Base):
    __tablename__ = "game_languages"

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), primary_key=True)
    language: Mapped[str] = mapped_column(primary_key=True)


class WordProgress(Base):
    __tablename__ = "word_progress"
    __table_args__ = (
        UniqueConstraint("word_id", "game_type", name="uq_word_progress_word_game"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), index=True)
    game_type: Mapped[str] = mapped_column(index=True)

    is_learning: Mapped[bool] = mapped_column(default=True)
    learning_step_index: Mapped[int] = mapped_column(default=0)
    interval_days: Mapped[float] = mapped_column(default=0.0)
    consecutive_correct: Mapped[int] = mapped_column(default=0)
    lapses: Mapped[int] = mapped_column(default=0)
    next_review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Set on every answer, including ones that do not change the schedule.
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    word: Mapped["Word"] = relationship(back_populates="progress", lazy="raise")
    review_logs: Mapped[list["ReviewLog"]] = relationship(
        back_populates="progress", cascade="all, delete-orphan", lazy="raise"
    )


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word_progress_id: Mapped[int] = mapped_column(ForeignKey("word_progress.id", ondelete="CASCADE"), index=True)
    grade: Mapped[str]  # AnswerGrade value directly — "wrong"/"close"/"correct"
    interval_at_review: Mapped[float]
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    progress: Mapped["WordProgress"] = relationship(back_populates="review_logs", lazy="raise")


class GameSettings(Base):
    """A user's spaced-repetition settings. No row means the defaults."""

    __tablename__ = "game_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    learning_steps_minutes: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    graduating_interval_days: Mapped[int]
    strict_mode: Mapped[bool]
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
