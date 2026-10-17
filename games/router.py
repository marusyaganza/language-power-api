"""HTTP interface for the games module.

Handlers only translate between HTTP and `games.service`: they read the
request, pass in the acting user, schedule background work, and map service
errors to status codes. What each operation does is documented on the service
functions.
"""
from contextlib import contextmanager

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from core.database import get_db
from games import service
from games.schemas import AnswerRequest, AnswerResponse, GameOut, GameSessionOut

router = APIRouter(prefix="/games", tags=["games"])

_STATUS_FOR_ERROR: dict[type[service.GamesError], int] = {
    service.GameNotFoundError: status.HTTP_404_NOT_FOUND,
    service.GameNotImplementedError: status.HTTP_501_NOT_IMPLEMENTED,
    service.SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    service.SessionGameMismatchError: status.HTTP_400_BAD_REQUEST,
    service.QuestionNotFoundError: status.HTTP_404_NOT_FOUND,
}


@contextmanager
def _http_errors():
    """Turn a `GamesError` raised inside the block into an `HTTPException`.

    An error missing from `_STATUS_FOR_ERROR` becomes a 500, so a new error
    type added to the service is never silently reported as a client error.
    """
    try:
        yield
    except service.GamesError as exc:
        raise HTTPException(
            status_code=_STATUS_FOR_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[GameOut])
async def list_games(
    language: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the games offered for a language, with how many saved words each can use."""
    return await service.list_games_for_language(db, user.id, language)


@router.get("/{game_id}", response_model=GameSessionOut)
async def start_game_session(
    game_id: int,
    language: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a game session with questions drawn from the user's saved words.

    404 if the game does not exist, 501 if its type cannot be played yet.
    """
    with _http_errors():
        return await service.start_game_session(db, user.id, game_id, language)


@router.post("/{game_id}/answer", response_model=AnswerResponse)
async def submit_answer(
    game_id: int,
    payload: AnswerRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Grade an answer in a running game session.

    404 if the session expired, belongs to another user, or has no such
    question, 400 if the session belongs to another game. The learning
    progress is saved after the response has been sent.
    """
    with _http_errors():
        check = await service.check_answer(
            user_id=user.id,
            session_id=payload.session_id,
            game_id=game_id,
            word_id=payload.word_id,
            answer=payload.answer,
        )

    background_tasks.add_task(
        service.persist_review_result,
        word_id=payload.word_id,
        game_type=check.game_type,
        grade=check.grade,
    )
    return AnswerResponse(
        grade=check.grade,
        correct_answer=check.correct_answer,
        session_complete=check.session_complete,
    )