from fastapi import APIRouter, Depends, Response, HTTPException, status, Cookie
from sqlalchemy.orm import Session

from core.database import get_db
from settings import settings
from users import service as users_service
from auth.schemas import UserCreate, UserOut
from auth.service import create_session, destroy_session
from auth.dependencies import get_current_user
from users.models import User
from auth.schemas import LoginRequest
from auth.helpers import set_session_cookie, clear_session_cookie

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
    set_session_cookie(response, session_id)
   

    return user

@auth_router.post("/login", response_model=UserOut)
def login(credentials: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = users_service.get_user_by_email(db, credentials.email)

    if user is None or not users_service.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    session_id = create_session(user.id)
    set_session_cookie(response, session_id)

    return user

@auth_router.post("/logout")
def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
):
    if session_id is not None:
        destroy_session(session_id)

    clear_session_cookie(response)

    return {"detail": "Logged out"}

@auth_router.get("/config")
def auth_config():
    return {"signup_enabled": settings.signup_enabled}


@auth_router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user