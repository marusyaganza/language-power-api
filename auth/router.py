"""HTTP interface for authentication.

Handlers only translate between HTTP and `auth.service`: they read the
request, set or clear the session cookie, and map service errors to status
codes. What each operation does is documented on the service functions.
"""
from contextlib import contextmanager

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import service
from auth.dependencies import get_current_user
from auth.helpers import clear_session_cookie, set_session_cookie
from auth.schemas import LoginRequest, UserCreate, UserOut
from core.database import get_db
from users.models import User

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_STATUS_FOR_ERROR: dict[type[service.AuthError], int] = {
    service.SignupClosedError: status.HTTP_403_FORBIDDEN,
    service.EmailAlreadyRegisteredError: status.HTTP_400_BAD_REQUEST,
    service.InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    service.TooManyAttemptsError: status.HTTP_429_TOO_MANY_REQUESTS,
}


@contextmanager
def _http_errors():
    """Turn an `AuthError` raised inside the block into an `HTTPException`.

    An error missing from `_STATUS_FOR_ERROR` becomes a 500, so a new error
    type added to the service is never silently reported as a client error.
    A 429 tells the client how long to wait in a `Retry-After` header.
    """
    try:
        yield
    except service.AuthError as exc:
        headers = None
        if isinstance(exc, service.TooManyAttemptsError):
            headers = {"Retry-After": str(exc.retry_after)}
        raise HTTPException(
            status_code=_STATUS_FOR_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=str(exc),
            headers=headers,
        ) from exc


@auth_router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    user_in: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Create an account and log in.

    403 if signups are closed, 400 if the email is taken, 429 (with
    `Retry-After`) after too many signups.
    """
    with _http_errors():
        result = await service.signup(db, user_in)
    set_session_cookie(response, result.session_id)
    return result.user


@auth_router.post("/login", response_model=UserOut)
async def login(
    credentials: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Log in with email and password.

    401 if either is wrong, 429 (with `Retry-After`) after too many attempts
    for this email.
    """
    with _http_errors():
        result = await service.login(db, credentials)
    set_session_cookie(response, result.session_id)
    return result.user


@auth_router.post("/logout")
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
):
    """Log out. Succeeds even if there is no session to end."""
    if session_id is not None:
        await service.destroy_session(session_id)
    clear_session_cookie(response)
    return {"detail": "Logged out"}


@auth_router.get("/config")
async def auth_config():
    """Public settings the frontend needs before anyone is logged in."""
    return {
        "signup_enabled": service.signups_open(),
        "use_mocks": service.mocks_enabled(),
    }


@auth_router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the logged-in user."""
    return current_user