from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from words.models import Word


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # auth.schemas lowercases input, so lookups can match exactly.
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    # Indexed for the daily signup count and deleting expired accounts.
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # passive_deletes: the database deletes a user's words (ON DELETE CASCADE),
    # so deleting a user doesn't load thousands of words just to delete them.
    words: Mapped[list["Word"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise", passive_deletes=True
    )
