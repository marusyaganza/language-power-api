"""HTTP interface for finding a word's image (personal deployment only).

Handlers only translate between HTTP and `images.service`. Every route answers
404 where image search is off (`settings.image_search_providers` empty),
before anything else is checked.
"""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from core.database import get_db
from images import service
from images.base import MAX_QUERY_LENGTH, ImageType
from images.schemas import ImageHitOut, ImageSearchOut, ImageSuggestionsOut, UsedImageOut
from settings import settings


def require_image_search():
    if not settings.image_search_providers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_image_search)])

_STATUS_FOR_ERROR: dict[type[service.ImagesError], int] = {
    service.InvalidSearchError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.WordNotFoundError: status.HTTP_404_NOT_FOUND,
    service.SearchBusyError: status.HTTP_503_SERVICE_UNAVAILABLE,
    service.SearchTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    service.SearchFailedError: status.HTTP_502_BAD_GATEWAY,
}


@contextmanager
def _http_errors():
    """Turn an `ImagesError` into an `HTTPException`; an unmapped one becomes a 500."""
    try:
        yield
    except service.ImagesError as exc:
        raise HTTPException(
            status_code=_STATUS_FOR_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR), detail=str(exc)
        ) from exc


@router.get("/search", response_model=ImageSearchOut)
async def search_images(
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    page: Annotated[int, Query(ge=1)] = 1,
    type: Annotated[ImageType, Query()] = ImageType.ALL,
    current_user=Depends(get_current_user),
):
    """One page of images for `q` (an English meaning), 12 at a time.

    Results are cached for 24 hours. 422 for an empty query or a page past
    the last one; 503 if the source is refusing requests for now, 504 if it
    timed out, 502 if it failed (all worth retrying).
    """
    with _http_errors():
        results = await service.search(q, page, type)
    return ImageSearchOut(
        source=service.search_source().source,
        # ImageHitOut has no `download_url`, so the response leaves it out.
        items=[ImageHitOut.model_validate(hit, from_attributes=True) for hit in results.items],
        total=results.total,
        page=results.page,
        has_more=results.has_more,
    )


@router.get("/suggestions", response_model=ImageSuggestionsOut)
async def image_suggestions(
    word_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """What the image picker starts with for one of your words: the query to search.

    404 if the word isn't one of yours.
    """
    with _http_errors():
        suggestions = await service.suggestions(db, current_user.id, word_id)
    return ImageSuggestionsOut(
        query=suggestions.query,
        used_before=[UsedImageOut(word_id=used.word_id, img_url=used.img_url) for used in suggestions.used_before],
    )
