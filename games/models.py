# games/models.py
import enum
from sqlalchemy import ForeignKey, UniqueConstraint, Column, DateTime, Boolean, Integer, String, Float, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


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

# games/models.py
class WordProgress(Base):
    __tablename__ = "word_progress"
    __table_args__ = (
        UniqueConstraint("word_id", "game_type", name="uq_word_progress_word_game"),
    )

    id = Column(Integer, primary_key=True, index=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    game_type = Column(String, nullable=False, index=True)

    is_learning = Column(Boolean, nullable=False, default=True)
    learning_step_index = Column(Integer, nullable=False, default=0)
    interval_days = Column(Float, nullable=False, default=0.0)
    consecutive_correct = Column(Integer, nullable=False, default=0)
    lapses = Column(Integer, nullable=False, default=0)
    next_review_date = Column(DateTime(timezone=True), nullable=False, index=True)
    # Set on every answer, including ones that do not change the schedule.
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    word = relationship("Word", back_populates="progress", lazy="raise")
    review_logs = relationship("ReviewLog", back_populates="progress", cascade="all, delete-orphan", lazy="raise")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)
    word_progress_id = Column(Integer, ForeignKey("word_progress.id", ondelete="CASCADE"), nullable=False, index=True)
    grade = Column(String, nullable=False)  # AnswerGrade value directly — "wrong"/"close"/"correct"
    interval_at_review = Column(Float, nullable=False)
    answered_at = Column(DateTime(timezone=True), server_default=func.now())

    progress = relationship("WordProgress", back_populates="review_logs", lazy="raise")


class GameSettings(Base):
    """A user's spaced-repetition settings. No row means the defaults."""

    __tablename__ = "game_settings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    learning_steps_minutes = Column(ARRAY(Integer), nullable=False)
    graduating_interval_days = Column(Integer, nullable=False)
    strict_mode = Column(Boolean, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
