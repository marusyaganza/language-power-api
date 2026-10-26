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

Logins and signups are rate-limited in memory (`auth.rate_limit`, limits in
`settings`): logins per email, signups all together.
"""
import asyncio
import math
import secrets
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from auth.rate_limit import AttemptLimiter
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
    "TooManyAttemptsError",
    "AuthResult",
    "signups_open",
    "mocks_enabled",
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


class TooManyAttemptsError(AuthError):
    """Too many attempts recently; `retry_after` is the whole seconds to wait."""

    def __init__(self, retry_after: int):
        super().__init__("Too many attempts, try again later")
        self.retry_after = retry_after


# --------------------------------------------------------------------------- #
# Signing up and logging in
# --------------------------------------------------------------------------- #

_login_limiter = AttemptLimiter(settings.login_attempt_limit, settings.login_attempt_window_seconds)
_signup_limiter = AttemptLimiter(settings.signup_limit, settings.signup_window_seconds)
# Every signup shares one count: the limit is on new accounts overall, and
# needs nothing from the request that a caller could vary.
_SIGNUP_KEY = "signup"


def _count_attempt(limiter: AttemptLimiter, key: str) -> None:
    """Count an attempt, or raise TooManyAttemptsError if the limit is reached."""
    wait = limiter.acquire(key)
    if wait is not None:
        raise TooManyAttemptsError(retry_after=math.ceil(wait))

@dataclass(frozen=True)
class AuthResult:
    """A user who has just been authenticated, and the session created for them."""

    user: User
    session_id: str


def signups_open() -> bool:
    """Whether new accounts can currently be created (the `signup_enabled` setting)."""
    return settings.signup_enabled


def mocks_enabled() -> bool:
    """Whether dictionary lookups use mock data (the `use_mocks` setting)."""
    return settings.use_mocks


async def signup(db: AsyncSession, user_in: UserCreate) -> AuthResult:
    """Create an account and start a session for it.

    The email check below is only the fast path: two simultaneous signups
    with the same email can both pass it. The database's unique index then
    rejects the second insert, and that is reported the same way.

    Every attempt while signups are open counts toward the signup limit,
    including one for a taken email.

    Raises:
        SignupClosedError: signups are turned off.
        TooManyAttemptsError: too many signups recently, from anyone.
        EmailAlreadyRegisteredError: the email belongs to an existing account.
    """
    if not signups_open():
        raise SignupClosedError("Signups are currently closed")
    _count_attempt(_signup_limiter, _SIGNUP_KEY)

    if await users_service.get_user_by_email(db, user_in.email) is not None:
        raise EmailAlreadyRegisteredError("Email already registered")

    try:
        user = await users_service.create_user(db, user_in)
    except users_service.EmailTakenError as exc:
        raise EmailAlreadyRegisteredError("Email already registered") from exc
    return AuthResult(user=user, session_id=await create_session(user.id))


async def login(db: AsyncSession, credentials: LoginRequest) -> AuthResult:
    """Check an email and password and start a session for the matching user.

    An unknown email and a wrong password raise the same error, so the
    response does not reveal which emails are registered. Timing is not
    equalized, though: an unknown email returns without hashing anything.

    Every attempt counts toward the email's limit, not only failed ones:
    the password check runs in a thread, so attempts made at the same time
    would all start before any of them failed. The count is taken before the
    database lookup and bcrypt, so a refused attempt costs nothing, and a
    successful login starts it over.

    Raises:
        TooManyAttemptsError: too many attempts for this email recently,
            even if the password is right.
        InvalidCredentialsError: unknown email or wrong password.
    """
    _count_attempt(_login_limiter, credentials.email)
    user = await users_service.get_user_by_email(db, credentials.email)
    # Password hashing is slow on purpose, so it runs in a thread to keep it
    # from stalling every other request on the event loop.
    if user is None or not await asyncio.to_thread(
        users_service.verify_password, credentials.password, user.hashed_password
    ):
        raise InvalidCredentialsError("Incorrect email or password")

    _login_limiter.reset(credentials.email)
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