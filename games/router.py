# games/router.py
from fastapi import APIRouter, Depends, Query, HTTPException
from games.service import list_games_for_language, start_word_recall_session
from auth.dependencies import get_current_user
from core.database import get_db
from games.schemas import GameOut, GameSessionOut
from games.models import Game

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