"""Dictionary providers that read made-up API responses instead of calling the API.

Used when the `use_mocks` setting is on (see `dictionary.providers`): in tests
and local development. The responses live in
`FIXTURES_DIR/<language>/<query>.json`, in the shape of the provider's
`_fetch_raw` answer, but written for this project (fixtures/README.md).

A few words get audio and a picture from `SAMPLE_MEDIA`: free files hosted
elsewhere (credited in fixtures/README.md), so the browser loads them directly.
"""

import json
from dataclasses import replace
from pathlib import Path

from core.language import Language
from dictionary.base import SearchResult
from dictionary.entry import DictionaryEntry

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_CAT_PICTURE = "https://picsum.photos/id/40/400/300"
# (language, word name) → audio_url and img_url.
SAMPLE_MEDIA = {
    (Language.EN, "cat"): {
        "audio_url": "https://upload.wikimedia.org/wikipedia/commons/transcoded/4/46/En-us-cat.ogg/En-us-cat.ogg.mp3",
        "img_url": _CAT_PICTURE,
    },
    (Language.ES, "gato"): {
        "audio_url": (
            "https://upload.wikimedia.org/wikipedia/commons/transcoded/c/c0/LL-Q1321_%28spa%29-Millars-gato.wav"
            "/LL-Q1321_%28spa%29-Millars-gato.wav.mp3"
        ),
        "img_url": _CAT_PICTURE,
    },
}


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
        result = await super().fetch(key)
        result.words = [self._with_sample_media(word) for word in result.words]
        return result

    async def _fetch_raw(self, query: str) -> list:
        return json.loads(self._fixtures[query].read_text(encoding="utf-8"))

    def _with_sample_media(self, word: DictionaryEntry) -> DictionaryEntry:
        """The entry with its sample audio and picture, where the word has them."""
        return replace(word, **SAMPLE_MEDIA.get((self.language, word.name.lower()), {}))
