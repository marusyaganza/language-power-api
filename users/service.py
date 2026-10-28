"""User accounts: creating them, looking them up, and checking passwords.

Passwords are only ever stored as bcrypt hashes. Hashing and verifying are
deliberately slow and CPU-bound, so they are plain synchronous functions;
async callers should run them with `asyncio.to_thread` (as `auth.service`
does) so they do not block the event loop.

`db` must be an `AsyncSession`.
"""

import asyncio
from datetime import datetime

import bcrypt
from psycopg.errors import UniqueViolation
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserCreate
from users.models import User

# The unique index on users.email (`email: Mapped[str] = mapped_column(unique=True, index=True)` in users/models.py).
EMAIL_UNIQUE_INDEX = "ix_users_email"

__all__ = [
    "EmailTakenError",
    "hash_password",
    "verify_password",
    "create_user",
    "get_user_by_id",
    "get_user_by_email",
    "count_users_created_since",
    "delete_users_created_before",
]


class EmailTakenError(Exception):
    """Another account already has this email."""


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of `password`, suitable for storing."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Whether `plain_password` matches a hash made by `hash_password`."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    """Store a new user with the password hashed, and return it.

    The database's unique index is what guarantees one account per email:
    a check before calling this can't, since two requests can both pass it
    before either inserts.

    Raises:
        EmailTakenError: the email is already registered. Nothing is stored
            and the session is rolled back. Any other database error is
            raised unchanged.
    """
    user = User(
        email=user_in.email,
        # Hashing is slow on purpose, so it runs in a thread to keep it from
        # stalling every other request on the event loop.
        hashed_password=await asyncio.to_thread(hash_password, user_in.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if isinstance(exc.orig, UniqueViolation) and exc.orig.diag.constraint_name == EMAIL_UNIQUE_INDEX:
            raise EmailTakenError(user_in.email) from exc
        raise
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Return the user with this id, or None."""
    return await db.scalar(select(User).where(User.id == user_id))


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return the user with this email, or None.

    The match is exact. Stored emails are lowercase, so pass `email` already
    lowercased, as `auth.schemas` does for every request.
    """
    return await db.scalar(select(User).where(User.email == email))


async def count_users_created_since(db: AsyncSession, since: datetime) -> int:
    """How many accounts were created at or after `since`."""
    return await db.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0


async def delete_users_created_before(db: AsyncSession, cutoff: datetime) -> int:
    """Delete every account created before `cutoff`, with all its data, and commit.

    The database deletes what the accounts own (ON DELETE CASCADE), so no
    rows are loaded. Returns how many accounts were deleted.
    """
    result = await db.execute(delete(User).where(User.created_at < cutoff))
    await db.commit()
    return result.rowcount
