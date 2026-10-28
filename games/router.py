"""HTTP interface for the games module.

Handlers only translate between HTTP and `games.service`: they read the
request, pass in the acting user, and map service errors to status codes.
What each operation does is documented on the service functions.
"""

from contextlib import contextmanager

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from core.database import get_db
from core.language import Language
from games import service
from games.schemas import (
    AnswerRequest,
    AnswerResponse,
    GameOut,
    GameResultOut,
    GameSessionCreate,
    GameSessionOut,
    GameSettingsOut,
    GameSettingsPreset,
    GameSettingsUpdate,
)

router = APIRouter(prefix="/games", tags=["games"])
# The settings belong to the logged-in user, hence /users/me rather than /games.
settings_router = APIRouter(prefix="/users/me/game-settings", tags=["games"])

_STATUS_FOR_ERROR: dict[type[service.GamesError], int] = {
    service.GameNotFoundError: status.HTTP_404_NOT_FOUND,
    service.GameNotImplementedError: status.HTTP_501_NOT_IMPLEMENTED,
    service.SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    service.QuestionNotFoundError: status.HTTP_404_NOT_FOUND,
    service.SessionFinishedError: status.HTTP_409_CONFLICT,
    service.QuestionAlreadyAnsweredError: status.HTTP_409_CONFLICT,
    service.NotEnoughWordsError: status.HTTP_409_CONFLICT,
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
    language: Language = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the games offered for a language, with how many saved words each can use and how many are due."""
    return await service.list_games_for_language(db, user.id, language)


@router.post(
    "/{game_id}/sessions",
    response_model=GameSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_game_session(
    game_id: int,
    payload: GameSessionCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a game session with questions drawn from the user's saved words.

    `mode=spaced` uses only due words, `mode=review` every word.
    `new_words_first` puts words never practiced in this game ahead of the rest.

    404 if the game does not exist, 501 if its type cannot be played yet,
    409 if the user has fewer words than the game's `min_word_count`.
    """
    with _http_errors():
        return await service.start_game_session(
            db, user.id, game_id, payload.language, payload.mode, payload.new_words_first
        )


# Session path parameters are not called `session_id`: `get_current_user`
# already reads the auth cookie under that name, and FastAPI cannot take both.
@router.post("/sessions/{game_session_id}/answers", response_model=AnswerResponse)
async def submit_answer(
    game_session_id: str,
    payload: AnswerRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grade an answer in a running game session.

    404 if the session expired, belongs to another user, or has no such
    question, 409 if the session is finished or the question was already
    answered. The learning progress is saved before the response is sent; a
    failure to save it is logged, not reported, since the answer has already
    been graded.
    """
    with _http_errors():
        check = await service.check_answer(
            user_id=user.id,
            session_id=game_session_id,
            word_id=payload.word_id,
            answer=payload.answer,
        )

    await service.persist_review_result(
        db,
        user_id=user.id,
        word_id=payload.word_id,
        game_type=check.game_type,
        grade=check.grade,
    )
    return AnswerResponse(
        grade=check.grade,
        correct_answer=check.correct_answer,
        session_complete=check.session_complete,
    )


@router.post("/sessions/{game_session_id}/result", response_model=GameResultOut)
async def get_game_result(game_session_id: str, user=Depends(get_current_user)):
    """Finish a game session (if still running) and return its result.

    Idempotent: calling it again on a finished session returns the same
    result. 404 if the session expired or belongs to another user.
    """
    with _http_errors():
        return await service.get_session_result(user.id, game_session_id)


@settings_router.get("", response_model=GameSettingsOut)
async def get_game_settings(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The user's spaced-repetition settings (the default preset's if never changed)."""
    return await service.get_game_settings(db, user.id)


@settings_router.put("", response_model=GameSettingsOut)
async def update_game_settings(
    payload: GameSettingsUpdate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the user's spaced-repetition settings.

    They apply to each word from its next answer; scheduled reviews keep
    their dates. 422 if the values are out of range or inconsistent.
    """
    return await service.update_game_settings(db, user.id, payload)


@settings_router.get("/presets", response_model=list[GameSettingsPreset])
async def list_game_settings_presets(user=Depends(get_current_user)):
    """The presets a user can pick from, the first being the default."""
    return service.list_game_settings_presets()
