"""FastAPI dependencies for identifying and limiting the caller."""

import math

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import service as auth_service
from auth.rate_limit import AttemptLimiter
from core.database import get_db
from core.proxy_signature import client_ip
from settings import settings
from users import service as users_service
from users.models import User

_request_limiter = AttemptLimiter(settings.request_ip_limit, settings.request_ip_window_seconds)


def _not_authenticated() -> HTTPException:
    # 401: the caller is not known (no valid session), as opposed to 403, a
    # known caller who is refused (e.g. signup closed). There is no standard
    # `WWW-Authenticate` scheme for a session cookie, so none is sent.
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_user(
    session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the user the request's session cookie belongs to.

    Also extends the session's lifetime when it is running low, so active
    users stay logged in.

    Raises:
        HTTPException: 401 if there is no cookie, the session is unknown or
            expired, or its user no longer exists or has expired
            (`auth.service.account_expired`). These cases are not
            distinguished, so a caller learns nothing about which sessions
            exist.
    """
    if session_id is None:
        raise _not_authenticated()

    user_id = await auth_service.get_user_id_for_session(session_id)
    if user_id is None:
        raise _not_authenticated()

    await auth_service.refresh_session_if_needed(session_id)

    user = await users_service.get_user_by_id(db, user_id)
    if user is None or auth_service.account_expired(user):
        # The session points at a user that was deleted, or whose account has
        # expired and is about to be.
        raise _not_authenticated()

    return user


async def limit_requests_per_ip(request: Request) -> None:
    """Refuse the request if its client IP has made too many recently.

    For every route behind the proxy signature, after the signature check
    (until then the IP can't be trusted) and before the session lookup, so a
    script can't use up the Redis command quota or keep the instance busy.
    Does nothing where the IP isn't known (`core.proxy_signature.client_ip`).

    Raises:
        HTTPException: 429 with `Retry-After`, the whole seconds to wait.
    """
    ip = client_ip(request)
    if ip is None:
        return
    wait = _request_limiter.acquire(ip)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
            headers={"Retry-After": str(math.ceil(wait))},
        )
