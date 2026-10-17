"""Authentication: signing up, logging in, and the server-side sessions behind them.

A session is a random id stored in Redis that maps to a user id and expires on
its own. The id is the only credential the client holds (it travels in a
cookie, see `auth.helpers`), so it is generated with `secrets` and never
derived from anything about the user.

Rules that apply to every function below:

* Failures are raised as subclasses of `AuthError`. This module knows nothing
  about HTTP or cookies; the router decides status codes and sets the cookie.
* `db` must be an `AsyncSession`, and `core.redis.redis_client` must be an
  asyncio client (`redis.asyncio.Redis`).
"""
import asyncio
import secrets
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import LoginRequest, UserCreate
from core.redis import redis_client
from settings import settings
from users import service as users_service
from users.models import User

__all__ = [
    "AuthError",
    "SignupClosedError",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "AuthResult",
    "signups_open",
    "signup",
    "login",
    "create_session",
    "get_user_id_for_session",
    "refresh_session_if_needed",
    "destroy_session",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class AuthError(Exception):
    """Base class for every error this module raises on purpose."""


class SignupClosedError(AuthError):
    """New accounts cannot be created right now."""


class EmailAlreadyRegisteredError(AuthError):
    """An account with this email already exists."""


class InvalidCredentialsError(AuthError):
    """The email or password is wrong. Deliberately does not say which."""


# --------------------------------------------------------------------------- #
# Signing up and logging in
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AuthResult:
    """A user who has just been authenticated, and the session created for them."""

    user: User
    session_id: str


def signups_open() -> bool:
    """Whether new accounts can currently be created (the `signup_enabled` setting)."""
    return settings.signup_enabled


async def signup(db: AsyncSession, user_in: UserCreate) -> AuthResult:
    """Create an account and start a session for it.

    The email check and the insert are not atomic. Two simultaneous signups
    with the same email can both pass the check, and the loser is then
    rejected by the database (if the email column is unique) as a database
    error rather than `EmailAlreadyRegisteredError`.

    Raises:
        SignupClosedError: signups are turned off.
        EmailAlreadyRegisteredError: the email belongs to an existing account.
    """
    if not signups_open():
        raise SignupClosedError("Signups are currently closed")

    if await users_service.get_user_by_email(db, user_in.email) is not None:
        raise EmailAlreadyRegisteredError("Email already registered")

    user = await users_service.create_user(db, user_in)
    return AuthResult(user=user, session_id=await create_session(user.id))


async def login(db: AsyncSession, credentials: LoginRequest) -> AuthResult:
    """Check an email and password and start a session for the matching user.

    An unknown email and a wrong password raise the same error, so the
    response does not reveal which emails are registered. Timing is not
    equalized, though: an unknown email returns without hashing anything.

    Raises:
        InvalidCredentialsError: unknown email or wrong password.
    """
    user = await users_service.get_user_by_email(db, credentials.email)
    # Password hashing is slow on purpose, so it runs in a thread to keep it
    # from stalling every other request on the event loop.
    if user is None or not await asyncio.to_thread(
        users_service.verify_password, credentials.password, user.hashed_password
    ):
        raise InvalidCredentialsError("Incorrect email or password")

    return AuthResult(user=user, session_id=await create_session(user.id))


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


async def create_session(user_id: int) -> str:
    """Start a session for `user_id` and return its id.

    The session expires `settings.session_ttl_seconds` after its last
    refresh (see `refresh_session_if_needed`).
    """
    session_id = secrets.token_urlsafe(32)
    await redis_client.set(
        _session_key(session_id),
        str(user_id),
        ex=settings.session_ttl_seconds,
    )
    return session_id


async def get_user_id_for_session(session_id: str) -> int | None:
    """Return the user the session belongs to, or None if it is unknown or has expired."""
    user_id = await redis_client.get(_session_key(session_id))
    return int(user_id) if user_id is not None else None


async def refresh_session_if_needed(session_id: str) -> None:
    """Restart the session's lifetime once less than half of it is left.

    Call this on authenticated requests so active users stay logged in. It
    only writes to Redis in the second half of the lifetime, which avoids a
    write on every request. Does nothing for a session that is unknown or
    already expired.
    """
    ttl = await redis_client.ttl(_session_key(session_id))
    if ttl <= 0:
        return  # key doesn't exist or has no TTL, so there is nothing to refresh

    if ttl < settings.session_ttl_seconds / 2:
        await redis_client.expire(_session_key(session_id), settings.session_ttl_seconds)


async def destroy_session(session_id: str) -> None:
    """End the session. Safe to call for a session that no longer exists."""
    await redis_client.delete(_session_key(session_id))