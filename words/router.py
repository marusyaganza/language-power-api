"""HTTP interface for the words module.

Handlers only translate between HTTP and `words.service`: they read the
request, pass in the acting user, and map service errors to status codes.
What each operation actually does is documented on the service functions.
"""

from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from core.database import get_db
from core.language import Language
from words import service
from words.schemas import (
    SortOrder,
    VocabularyPage,
    VocabularySortBy,
    WordCreate,
    WordOut,
    WordSearchResponse,
    WordUpdate,
)

router = APIRouter(prefix="/words", tags=["words"])

_STATUS_FOR_ERROR: dict[type[service.WordsError], int] = {
    service.UnsupportedLanguageError: status.HTTP_400_BAD_REQUEST,
    service.DefinitionNotFoundError: status.HTTP_404_NOT_FOUND,
    service.DictionaryUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    service.WordNotFoundError: status.HTTP_404_NOT_FOUND,
    service.WordAlreadySavedError: status.HTTP_409_CONFLICT,
}


@contextmanager
def _http_errors():
    """Turn a `WordsError` raised inside the block into an `HTTPException`.

    An error missing from `_STATUS_FOR_ERROR` becomes a 500, so a new error
    type added to the service is never silently reported as a client error.
    """
    try:
        yield
    except service.WordsError as exc:
        raise HTTPException(
            status_code=_STATUS_FOR_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=str(exc),
        ) from exc


@router.get("/search", response_model=WordSearchResponse)
async def search_words(
    query: str,
    language: Language,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Search the dictionary, flagging words the user has already saved.

    404 if the dictionary has no entry,
    503 if the dictionary itself failed (worth retrying later).
    Spelling suggestions are a normal 200 response.
    """
    with _http_errors():
        return await service.search_words(db, current_user.id, query=query, language=language)


@router.post("/save", response_model=WordOut, status_code=status.HTTP_201_CREATED)
async def create_word(
    payload: WordCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Save a word to the user's vocabulary. 409 if it is already saved."""
    with _http_errors():
        return await service.save_word(db, current_user.id, payload)


@router.get("/vocabulary", response_model=VocabularyPage)
async def list_vocabulary(
    language: Language,
    query: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    sort_by: VocabularySortBy = Query(default=VocabularySortBy.created_at),
    sort_order: SortOrder | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return one page of the user's saved words in a language.

    Without `sort_order`, names sort A–Z and dates newest first.
    """
    with _http_errors():
        return await service.get_vocabulary_page(
            db,
            current_user.id,
            language=language,
            query=query,
            page=page,
            sort_by=sort_by,
            sort_order=sort_order,
        )


@router.patch("/{word_id}", response_model=WordOut)
async def edit_word(
    word_id: int,
    payload: WordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Edit a saved word. Fields left out of the body are unchanged. 404 if not found."""
    with _http_errors():
        return await service.update_word(db, current_user.id, word_id, payload)


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_word(
    word_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a saved word. 404 if the user has no such word."""
    with _http_errors():
        await service.delete_word(db, current_user.id, word_id)
