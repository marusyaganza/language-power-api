"""Pixabay: free photos and illustrations, searched in English.

Terms that shape this class (API docs, read 2026-11-08):
- At most 100 requests a minute per key; more answers 429.
- Answers must be cached for 24 hours (`ImageSearch.search` does).
- Result URLs may be shown "for temporarily displaying search results", but
  not hotlinked for good: a picked image is downloaded and stored.
- `webformatURL` is valid for 24 hours, so `get` asks again at save time.
- At most 500 results per query can be paged through (`totalHits`).
- Show where images come from whenever results are displayed (the client's job).
"""

import logging

import httpx

from core.image_source import ImageSource
from images.base import ImageSearch, ImageSearchBusyError, ImageSearchError, ImageSearchTimeoutError, ImageType
from images.results import PAGE_SIZE, ImageHit, ImageResults

logger = logging.getLogger(__name__)

API_URL = "https://pixabay.com/api/"
REQUEST_TIMEOUT_SECONDS = 10


class PixabayImageSearch(ImageSearch):
    source = ImageSource.PIXABAY
    max_results = 500

    def __init__(self, api_key: str, safe_search: bool = True):
        self._api_key = api_key
        self._safe_search = safe_search

    def cache_variant(self) -> str:
        return "safesearch-on" if self._safe_search else "safesearch-off"

    async def _search_raw(self, query: str, page: int, image_type: ImageType) -> ImageResults:
        data = await self._request(
            {
                "q": query,
                "page": page,
                "per_page": PAGE_SIZE,
                "image_type": str(image_type),
                "safesearch": "true" if self._safe_search else "false",
                "lang": "en",
            }
        )
        return ImageResults(items=_hits(data), total=_total(data), page=page)

    async def _get_raw(self, image_id: str) -> ImageHit | None:
        # Pixabay's ids are numbers; anything else can't be one, so don't ask.
        if not image_id.isascii() or not image_id.isdigit():
            return None
        hits = _hits(await self._request({"id": image_id}))
        return next((hit for hit in hits if hit.id == image_id), None)

    async def _request(self, params: dict) -> dict:
        """Pixabay's JSON answer for these parameters (the key is added here).

        Raises:
            ImageSearchTimeoutError, ImageSearchBusyError, ImageSearchError.
            Messages name only the kind of failure: httpx's own messages
            include the URL, and the URL includes the key.
        """
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(API_URL, params={"key": self._api_key, **params})
        except httpx.TimeoutException:
            raise ImageSearchTimeoutError("Pixabay didn't answer in time") from None
        except httpx.HTTPError as exc:
            raise ImageSearchError(f"Pixabay request failed: {type(exc).__name__}") from None
        if resp.status_code == 429:
            raise ImageSearchBusyError("Pixabay refused the request: too many requests")
        if resp.status_code != 200:
            raise ImageSearchError(f"Pixabay answered with status {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise ImageSearchError("Pixabay answered with something other than JSON") from None
        if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
            raise ImageSearchError("Pixabay answered without a list of hits")
        return data


def _total(data: dict) -> int:
    total = data.get("totalHits")
    return total if isinstance(total, int) and total >= 0 else 0


def _hits(data: dict) -> list[ImageHit]:
    """The hits of an answer, skipping (and logging) any with an unexpected shape."""
    hits = []
    for raw in data["hits"]:
        try:
            hits.append(_hit(raw))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipped a Pixabay hit with an unexpected shape: %s", type(exc).__name__)
    return hits


def _hit(raw: dict) -> ImageHit:
    strings = {name: raw[name] for name in ("previewURL", "webformatURL", "largeImageURL", "pageURL")}
    if not all(isinstance(value, str) and value.startswith("https://") for value in strings.values()):
        raise ValueError("an image URL isn't https")
    width, height = raw["webformatWidth"], raw["webformatHeight"]
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise ValueError("bad size")
    return ImageHit(
        id=str(int(raw["id"])),
        thumb_url=strings["previewURL"],
        preview_url=strings["webformatURL"],
        download_url=strings["largeImageURL"],
        width=width,
        height=height,
        page_url=strings["pageURL"],
        author=str(raw.get("user") or ""),
    )
