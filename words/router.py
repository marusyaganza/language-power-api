from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from core.database import get_db
from words.service import save_word, get_vocabulary_page, delete_word, update_word
from words.repository import get_saved_uuids
from words.schemas import WordOut, WordCreate, VocabularyPage, VocabularySortBy, WordUpdate
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

@router.get("/words/vocabulary", response_model=VocabularyPage)
def vocabulary(
    language: str,
    query: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    sort_by: VocabularySortBy = Query(default=VocabularySortBy.created_at),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_vocabulary_page(
        db, current_user.id, language=language, query=query, page=page, sort_by=sort_by
    )

@router.delete("/words/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    delete_word(db, current_user.id, word_id)

@router.patch("/words/{word_id}", response_model=WordOut)
def edit_word(
    word_id: int,
    payload: WordUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return update_word(db, current_user.id, word_id, payload)