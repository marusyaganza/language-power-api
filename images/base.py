from abc import ABC, abstractmethod
from enum import StrEnum

from core.image_source import ImageSource
from images import search_cache
from images.results import PAGE_SIZE, ImageHit, ImageResults

# The longest query: Pixabay's limit for `q`.
MAX_QUERY_LENGTH = 100


class ImageType(StrEnum):
    """Which kind of images a search returns."""

    ALL = "all"
    PHOTO = "photo"
    ILLUSTRATION = "illustration"


class ImageSearchError(Exception):
    """The search API could not be reached or answered with something unusable.

    The message is safe to log and show: it never contains the API key.
    """


class ImageSearchTimeoutError(ImageSearchError):
    """The search API didn't answer in time."""


class ImageSearchBusyError(ImageSearchError):
    """The search API refused the request: too many in a short time (HTTP 429)."""


def clean_query(query: str) -> str:
    """The query with its spaces trimmed and collapsed.

    Raises:
        ValueError: nothing is left, or it is longer than `MAX_QUERY_LENGTH`.
    """
    query = " ".join(query.split())
    if not query:
        raise ValueError("The image search query is empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"The image search query is longer than {MAX_QUERY_LENGTH} characters")
    return query


class ImageSearch(ABC):
    """One image search API: finds images for an English query, and one image by its id.

    Each API has its own class, like each language has its own dictionary
    provider. The rest of the app only calls `search` and `get`.

    `search` checks its arguments and keeps every answer in Redis for 24 hours
    (`search_cache`; Pixabay requires it), then calls `_search_raw` on a miss.
    `get` is never cached: it is called when a word is saved with a picked
    image, and must return a fresh `download_url` (Pixabay's expire after 24 h).
    """

    source: ImageSource
    # The most results the API lets you page through for one query.
    max_results: int

    @property
    def max_page(self) -> int:
        return -(-self.max_results // PAGE_SIZE)

    @abstractmethod
    def cache_variant(self) -> str:
        """What else, besides the arguments of `search`, changes its results (e.g. safe search)."""

    async def search(self, query: str, page: int = 1, image_type: ImageType = ImageType.ALL) -> ImageResults:
        """Page `page` (from 1) of the images found for `query`, `PAGE_SIZE` at a time.

        Raises:
            ValueError: the query is empty or too long, or `page` is outside 1–`max_page`.
            ImageSearchTimeoutError, ImageSearchBusyError, ImageSearchError: the API failed.
        """
        query = clean_query(query)
        if not 1 <= page <= self.max_page:
            raise ValueError(f"The page must be between 1 and {self.max_page}")
        key = search_cache.key(self.source, self.cache_variant(), query, page, image_type)
        cached = await search_cache.get(key)
        if cached is not None:
            return cached
        results = await self._search_raw(query, page, image_type)
        await search_cache.put(key, results)
        return results

    async def get(self, image_id: str) -> ImageHit | None:
        """The image with this id, or None if the API doesn't have it (anymore).

        Raises:
            ImageSearchTimeoutError, ImageSearchBusyError, ImageSearchError: the API failed.
        """
        return await self._get_raw(image_id)

    @abstractmethod
    async def _search_raw(self, query: str, page: int, image_type: ImageType) -> ImageResults:
        """Ask the API; the arguments are already checked. Raises as `search`."""

    @abstractmethod
    async def _get_raw(self, image_id: str) -> ImageHit | None:
        """Ask the API for one image. Raises as `get`."""
