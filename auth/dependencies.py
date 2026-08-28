from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from settings import settings
from auth import service as auth_service
from users import service as users_service
from users.models import User


def get_current_user(
    session_id: str | None = Cookie(default=None, alias=None),
    db: Session = Depends(get_db),
) -> User:
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")

    user_id = auth_service.get_user_id_for_session(session_id)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")

    auth_service.refresh_session_if_needed(session_id)

    user = users_service.get_user_by_id(db, user_id)
    if user is None:
        # Session pointed at a user that no longer exists — treat as unauthenticated
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")

    return user