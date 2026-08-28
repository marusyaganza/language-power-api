from fastapi import APIRouter, Depends, Response, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from settings import settings
from users import service as users_service
from users.schemas import UserCreate, UserOut
from auth.service import create_session
from auth.dependencies import get_current_user
from users.models import User

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, response: Response, db: Session = Depends(get_db)):
    if not settings.signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are currently closed",
        )

    existing_user = users_service.get_user_by_email(db, user_in.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = users_service.create_user(db, user_in)

    session_id = create_session(user.id)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )

    return user

@auth_router.get("/config")
def auth_config():
    return {"signup_enabled": settings.signup_enabled}


@auth_router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user