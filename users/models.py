from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # auth.schemas lowercases input, so lookups can match exactly.
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    words = relationship("Word", back_populates="user", cascade="all, delete-orphan", lazy="raise")