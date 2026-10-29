"""Dictionary providers that read made-up API responses instead of calling the API.

Used when the `use_mocks` setting is on (see `dictionary.providers`): in tests
and local development. The responses live in
`FIXTURES_DIR/<language>/<query>.json`, in the shape of the provider's
`_fetch_raw` answer, but written for this project (fixtures/README.md).

Audio and pictures for some words are in `SAMPLE_MEDIA_DIR/<language>/`, named
`<word>.mp3` and `<word>.svg`. `main` serves them at `SAMPLE_MEDIA_PATH`, and
the mock providers point the entries' `audio_url` and `img_url` at them.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

from core.language import Language
from dictionary.base import SearchResult
from dictionary.entry import DictionaryEntry
from settings import settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MEDIA_DIR = FIXTURES_DIR / "media"
SAMPLE_MEDIA_PATH = "/sample-media"
_SAMPLE_MEDIA_FILE_RE = re.compile(r"(en|es)/[a-z]+\.(mp3|svg)")


def sample_media_url(language: Language, filename: str) -> str:
    """The URL of a sample media file, as the browser sees it (with `settings.root_path`)."""
    return f"{settings.root_path}{SAMPLE_MEDIA_PATH}/{language}/{filename}"


def is_sample_media_url(url: str) -> bool:
    """Whether `url` is one `sample_media_url` could have made. Only in mock mode."""
    prefix = f"{settings.root_path}{SAMPLE_MEDIA_PATH}/"
    return (
        settings.use_mocks
        and url.startswith(prefix)
        and _SAMPLE_MEDIA_FILE_RE.fullmatch(url.removeprefix(prefix)) is not None
    )


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
        self._media = {path.name for path in (SAMPLE_MEDIA_DIR / self.language).glob("*")}

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
        media = {}
        for field, extension in (("audio_url", "mp3"), ("img_url", "svg")):
            filename = f"{word.name.lower()}.{extension}"
            if filename in self._media:
                media[field] = sample_media_url(self.language, filename)
        return replace(word, **media)
