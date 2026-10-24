"""User accounts: creating them, looking them up, and checking passwords.

Passwords are only ever stored as bcrypt hashes. Hashing and verifying are
deliberately slow and CPU-bound, so they are plain synchronous functions;
async callers should run them with `asyncio.to_thread` (as `auth.service`
does) so they do not block the event loop.

`db` must be an `AsyncSession`.
"""
import asyncio

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserCreate
from users.models import User

__all__ = [
    "hash_password",
    "verify_password",
    "create_user",
    "get_user_by_id",
    "get_user_by_email",
]


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

    Does not check that the email is unused. If the email column is unique,
    a duplicate surfaces as a database `IntegrityError`.
    """
    user = User(
        email=user_in.email,
        # Hashing is slow on purpose, so it runs in a thread to keep it from
        # stalling every other request on the event loop.
        hashed_password=await asyncio.to_thread(hash_password, user_in.password),
    )
    db.add(user)
    await db.commit()
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