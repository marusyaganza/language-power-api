"""Dictionary providers that read saved API responses instead of calling the API.

Used when the `use_mocks` setting is on (see `dictionary.providers`). The
responses live in `FIXTURES_DIR/<language>/<query>.json`: each is a real
provider's `_fetch_raw` answer, saved as it was received.
"""

import json
from pathlib import Path

from dictionary.base import SearchResult
from words.language import Language

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class MockDictionaryMixin:
    """Serve a real provider's responses from fixtures.

    Put it first in the bases, before the real provider, so that provider still
    formats the responses: `class Mock(MockDictionaryMixin, RealProvider)`.

    A query is trimmed and lowercased, then looked up among the fixture names;
    it is never used as a path. A query without a fixture returns
    `mock_queries`: every query that has one, sorted.
    """

    language: Language

    def __init__(self) -> None:
        self._fixtures = {path.stem: path for path in (FIXTURES_DIR / self.language).glob("*.json")}

    async def fetch(self, query: str) -> SearchResult:
        key = query.strip().lower()
        if key not in self._fixtures:
            return SearchResult(mock_queries=sorted(self._fixtures))
        return await super().fetch(key)

    async def _fetch_raw(self, query: str) -> list:
        return json.loads(self._fixtures[query].read_text(encoding="utf-8"))
