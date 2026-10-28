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
`settings`): logins per email, signups all together. Where the caller's IP is
known (`core.proxy_signature.client_ip`), logins are counted per IP and email
instead, and each IP also has its own login and signup limits. Where they are set,
`settings.daily_signup_limit` caps new accounts per UTC day, and
`settings.account_ttl_hours` limits how long an account lives.
"""

import asyncio
import math
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.rate_limit import AttemptLimiter
from auth.schemas import LoginRequest, UserCreate
from core import utc_day
from core.redis import redis_client
from settings import settings
from users import service as users_service
from users.models import User

__all__ = [
    "AuthError",
    "SignupClosedError",
    "SignupClosedForTodayError",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "TooManyAttemptsError",
    "AuthResult",
    "signups_open",
    "signup_open_today",
    "mocks_enabled",
    "account_expired",
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


class SignupClosedForTodayError(AuthError):
    """Today's new accounts are all taken; `retry_after` is the whole seconds until the next UTC day."""

    def __init__(self, retry_after: int):
        super().__init__("Sorry, registration is closed for today, try again tomorrow")
        self.retry_after = retry_after


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
_login_ip_limiter = AttemptLimiter(settings.login_ip_limit, settings.login_attempt_window_seconds)
_signup_ip_limiter = AttemptLimiter(settings.signup_ip_limit, settings.signup_window_seconds)
# Every signup shares one count: the limit is on new accounts overall, and
# needs nothing from the request that a caller could vary.
_SIGNUP_KEY = "signup"


@dataclass
class _DailyCount:
    day: date | None = None
    count: int = 0


# Accounts created today (UTC), for `settings.daily_signup_limit`. Read from
# the database once a day, then counted here: `/auth/config` asks for it on
# every call, including the uptime check's, and a query each time would keep
# the database from ever going idle. Exact because there is one instance.
_signups_today = _DailyCount()


async def _count_signups_today(db: AsyncSession, now: datetime) -> int:
    today = now.date()
    if _signups_today.day != today:
        count = await users_service.count_users_created_since(db, utc_day.start_of_day(now))
        _signups_today.day, _signups_today.count = today, count
    return _signups_today.count


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


async def signup_open_today(db: AsyncSession) -> bool:
    """Whether signups are open and today's limit (`daily_signup_limit`), if any, isn't reached."""
    if not signups_open():
        return False
    limit = settings.daily_signup_limit
    return limit is None or await _count_signups_today(db, utc_day.now()) < limit


def account_expired(user: User) -> bool:
    """Whether the account is older than `settings.account_ttl_hours` (never, if unset)."""
    ttl = settings.account_ttl_hours
    return ttl is not None and user.created_at is not None and user.created_at <= utc_day.now() - timedelta(hours=ttl)


def mocks_enabled() -> bool:
    """Whether dictionary lookups use mock data (the `use_mocks` setting)."""
    return settings.use_mocks


async def signup(db: AsyncSession, user_in: UserCreate, *, client_ip: str | None = None) -> AuthResult:
    """Create an account and start a session for it.

    The email check below is only the fast path: two simultaneous signups
    with the same email can both pass it. The database's unique index then
    rejects the second insert, and that is reported the same way.

    Every attempt while signups are open counts toward the signup limits
    (the IP's, if `client_ip` is known, then everyone's), including one for
    a taken email. Accounts older than
    `settings.account_ttl_hours` are deleted first, so a new account never
    meets an expired one with the same email.

    Raises:
        SignupClosedError: signups are turned off.
        SignupClosedForTodayError: today's new accounts are all taken.
            Checked before anything else; two signups at once can go one
            account over, which is fine.
        TooManyAttemptsError: too many signups recently, from this IP or
            from anyone.
        EmailAlreadyRegisteredError: the email belongs to an existing account.
    """
    if not signups_open():
        raise SignupClosedError("Signups are currently closed")
    now = utc_day.now()
    limit = settings.daily_signup_limit
    if limit is not None and await _count_signups_today(db, now) >= limit:
        raise SignupClosedForTodayError(retry_after=utc_day.seconds_until_next_day(now))
    if client_ip is not None:
        _count_attempt(_signup_ip_limiter, client_ip)
    _count_attempt(_signup_limiter, _SIGNUP_KEY)
    if settings.account_ttl_hours is not None:
        await users_service.delete_users_created_before(db, now - timedelta(hours=settings.account_ttl_hours))

    if await users_service.get_user_by_email(db, user_in.email) is not None:
        raise EmailAlreadyRegisteredError("Email already registered")

    try:
        user = await users_service.create_user(db, user_in)
    except users_service.EmailTakenError as exc:
        raise EmailAlreadyRegisteredError("Email already registered") from exc
    if _signups_today.day == now.date():
        _signups_today.count += 1
    return AuthResult(user=user, session_id=await create_session(user.id))


async def login(db: AsyncSession, credentials: LoginRequest, *, client_ip: str | None = None) -> AuthResult:
    """Check an email and password and start a session for the matching user.

    An unknown email and a wrong password raise the same error, so the
    response does not reveal which emails are registered. Timing is not
    equalized, though: an unknown email returns without hashing anything.

    Every attempt counts toward the email's limit, not only failed ones:
    the password check runs in a thread, so attempts made at the same time
    would all start before any of them failed. The count is taken before the
    database lookup and bcrypt, so a refused attempt costs nothing, and a
    successful login starts it over.

    With `client_ip`, the email's limit is counted per IP, so nobody can
    lock someone else out of their account from elsewhere, and all of the
    IP's attempts together have a limit too, so one IP can't try many emails
    (or fill the limiter's table of emails).

    An expired account (`account_expired`) is treated like an unknown email.

    Raises:
        TooManyAttemptsError: too many attempts for this email (from this
            IP) or from this IP recently, even if the password is right.
        InvalidCredentialsError: unknown email or wrong password.
    """
    if client_ip is not None:
        _count_attempt(_login_ip_limiter, client_ip)
    login_key = credentials.email if client_ip is None else f"{client_ip} {credentials.email}"
    _count_attempt(_login_limiter, login_key)
    user = await users_service.get_user_by_email(db, credentials.email)
    # Password hashing is slow on purpose, so it runs in a thread to keep it
    # from stalling every other request on the event loop.
    if (
        user is None
        or account_expired(user)
        or not await asyncio.to_thread(users_service.verify_password, credentials.password, user.hashed_password)
    ):
        raise InvalidCredentialsError("Incorrect email or password")

    _login_limiter.reset(login_key)
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
