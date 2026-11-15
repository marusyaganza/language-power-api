"""An image search that makes up Pixabay's answers instead of calling it.

Used when the `use_mocks` setting is on (see `images.searches`): in tests and
local development. Only the HTTP request is replaced, so the parsing, checks
and cache are the real ones.

The images are Lorem Picsum photos (free, hosted elsewhere, like the
dictionary mock's cat picture), so the browser loads them directly. Every
query finds `MOCK_RESULTS` of them, in an order that depends on the query,
except the queries in `NO_RESULTS`, which find nothing. The image type is
ignored: Picsum has photos only.
"""

import hashlib

from images.pixabay import PixabayImageSearch

# Lorem Picsum ids 0–84 all exist (some later ids don't).
PICSUM_IDS = 85
MOCK_RESULTS = 30
# Mock ids look like Pixabay's (numbers) and map back to a Picsum id.
ID_BASE = 1_000_000
NO_RESULTS = frozenset({"although", "nothing"})


def mock_hit(picsum_id: int) -> dict:
    """One hit in Pixabay's shape, for a Picsum photo."""
    base = f"https://picsum.photos/id/{picsum_id}"
    return {
        "id": ID_BASE + picsum_id,
        "previewURL": f"{base}/150/100",
        "webformatURL": f"{base}/640/427",
        "webformatWidth": 640,
        "webformatHeight": 427,
        "largeImageURL": f"{base}/1280/853",
        "pageURL": "https://picsum.photos/",
        "user": "Lorem Picsum",
    }


def mock_picsum_ids(query: str) -> list[int]:
    """The `MOCK_RESULTS` photos a query finds: the same query, the same photos."""
    if query.casefold() in NO_RESULTS:
        return []
    start = int(hashlib.sha256(query.casefold().encode()).hexdigest(), 16) % PICSUM_IDS
    return [(start + i * 7) % PICSUM_IDS for i in range(MOCK_RESULTS)]


class MockPixabayImageSearch(PixabayImageSearch):
    def __init__(self, api_key: str = "", safe_search: bool = True):
        super().__init__(api_key, safe_search)
        self.requests: list[dict] = []  # what reached "Pixabay", for tests of the cache

    async def _request(self, params: dict) -> dict:
        self.requests.append(params)
        if "id" in params:
            picsum_id = int(params["id"]) - ID_BASE
            hits = [mock_hit(picsum_id)] if 0 <= picsum_id < PICSUM_IDS else []
            return {"total": len(hits), "totalHits": len(hits), "hits": hits}
        ids = mock_picsum_ids(params["q"])
        start = (params["page"] - 1) * params["per_page"]
        hits = [mock_hit(picsum_id) for picsum_id in ids[start : start + params["per_page"]]]
        return {"total": len(ids), "totalHits": len(ids), "hits": hits}
