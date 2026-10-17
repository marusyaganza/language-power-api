"""FastAPI dependencies for identifying the caller."""
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import service as auth_service
from core.database import get_db
from users import service as users_service
from users.models import User


def _not_authenticated() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")


async def get_current_user(
    session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the user the request's session cookie belongs to.

    Also extends the session's lifetime when it is running low, so active
    users stay logged in.

    Raises:
        HTTPException: 403 if there is no cookie, the session is unknown or
            expired, or its user no longer exists. These cases are not
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
    if user is None:
        # The session points at a user that was deleted.
        raise _not_authenticated()

    return user