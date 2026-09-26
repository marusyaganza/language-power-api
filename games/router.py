# games/router.py
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from games.service import list_games_for_language, start_word_recall_session, persist_review_result
from auth.dependencies import get_current_user
from core.database import get_db
from games.schemas import GameOut, GameSessionOut, AnswerRequest, AnswerResponse
from games.models import Game
from games.constants import GAME_ANSWER_TYPES
from games.scoring import classify_typed_answer, classify_choice_answer
from games.session_store import get_game_session, get_question, mark_question_answered, GameSessionNotFound
from games.scoring import classify_typed_answer, classify_choice_answer, AnswerGrade

router = APIRouter(prefix="/games", tags=["games"])

@router.get("", response_model=list[GameOut])
def get_games(
    language: str = Query(...),
    practice_all: bool = Query(False),
    user=Depends(get_current_user),
    session=Depends(get_db),
):
    return list_games_for_language(session, user.id, language)

@router.get("/{game_id}", response_model=GameSessionOut)
def get_game_session(
    game_id: int,
    language: str = Query(...),
    user=Depends(get_current_user),
    session=Depends(get_db),
):
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.game_type != "type_word":
        raise HTTPException(status_code=501, detail="This game isn't implemented yet")

    return start_word_recall_session(session, user.id, game, language)

@router.post("/{game_id}/answer", response_model=AnswerResponse)
def submit_answer(
    game_id: int,
    payload: AnswerRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    try:
        session_data = get_game_session(payload.session_id)
    except GameSessionNotFound:
        raise HTTPException(status_code=404, detail="Session expired or not found")

    if session_data["game_id"] != game_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this game")

    try:
        question = get_question(session_data, payload.word_id)
    except GameSessionNotFound:
        raise HTTPException(status_code=404, detail="Question not found in session")

    game_type = session_data["game_type"]
    answer_type = GAME_ANSWER_TYPES.get(game_type, "choice")
    grade = (
        classify_typed_answer(payload.answer, question["answer"])
        if answer_type == "typed"
        else classify_choice_answer(payload.answer, question["answer"])
    )

    session_complete = mark_question_answered(payload.session_id, session_data, payload.word_id)

    background_tasks.add_task(
        persist_review_result,
        word_id=payload.word_id,
        game_type=game_type,
        grade=grade,
    )

    return AnswerResponse(
        grade=grade,
        correct_answer=None if grade == AnswerGrade.CORRECT else question["answer"],
        session_complete=session_complete,
    )