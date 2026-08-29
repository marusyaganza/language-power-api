from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from words.service import save_word
from words.repository import get_saved_uuids

from words.schemas import WordOut, WordCreate
from dictionary.providers import PROVIDERS
from auth.dependencies import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/words/search", response_model=list[WordOut])
async def search_word(
    query: str,
    language: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    provider = PROVIDERS.get(language)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    results = await provider.fetch(query)

    if not results:
        raise HTTPException(status_code=404, detail="Word not found")

    uuids = [w.uuid for w in results if w.uuid]
    saved_uuids = get_saved_uuids(db, current_user.id, uuids)

    output = [
        WordOut.model_validate(w).model_copy(update={"saved": w.uuid in saved_uuids})
        for w in results
    ]

    return output


@router.post("/words/save", response_model=WordOut, status_code=201)
def create_word(
    payload: WordCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return save_word(db, current_user.id, payload)