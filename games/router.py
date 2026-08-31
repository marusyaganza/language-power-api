# games/router.py
from fastapi import APIRouter, Depends, Query
from games.service import list_games_for_language
from auth.dependencies import get_current_user
from core.database import get_db
from games.schemas import GameOut

router = APIRouter(prefix="/games", tags=["games"])

@router.get("", response_model=list[GameOut])
def get_games(
    language: str = Query(...),
    practice_all: bool = Query(False),
    user=Depends(get_current_user),
    session=Depends(get_db),
):
    return list_games_for_language(session, user.id, language)