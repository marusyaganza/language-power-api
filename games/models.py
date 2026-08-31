# games/models.py
import enum
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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

    languages: Mapped[list["GameLanguage"]] = relationship(cascade="all, delete-orphan")

class GameLanguage(Base):
    __tablename__ = "game_languages"
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), primary_key=True)
    language: Mapped[str] = mapped_column(primary_key=True)