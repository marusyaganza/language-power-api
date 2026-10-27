from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from dictionary.entry import DictionaryEntry
from words.language import Language


@dataclass
class SearchResult:
    """A dictionary lookup: entries, or spelling suggestions when nothing matched.

    `mock_queries` is set only by the mock providers, for a query that has no
    fixture: the queries that do.
    """

    words: list[DictionaryEntry] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    mock_queries: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.words)

    @property
    def is_empty(self) -> bool:
        return not (self.words or self.suggestions or self.mock_queries)


class DictionaryError(Exception):
    """The dictionary could not be reached or did not answer usably.

    Not raised for a word the dictionary does not know: that is an empty
    `SearchResult`. The message is safe to log and never contains credentials.
    """


class DictionaryProvider(ABC):
    """One language's dictionary, backed by one external API.

    Each language has its own provider, so a language can change API without
    touching the others. The rest of the app only calls `fetch`.

    A lookup is split in two so the mock providers (`dictionary.mock`) can
    replace the request with a recorded answer and still run the real
    parsing: `_fetch_raw` returns the API's answer as it was received (what
    the fixtures store), and `_parse` turns it into a `SearchResult`.
    """

    language: Language

    async def fetch(self, query: str) -> SearchResult:
        """Look `query` up and return the entries or suggestions.

        Raises:
            DictionaryError: the dictionary is unreachable, timed out, or
                answered with an error or an unexpected response.
        """
        return self._parse(await self._fetch_raw(query))

    @abstractmethod
    async def _fetch_raw(self, query: str) -> Any:
        """Request `query` from the API and return its answer, unparsed.

        Raises:
            DictionaryError: as for `fetch`. The message must never contain
                credentials.
        """

    @abstractmethod
    def _parse(self, raw: Any) -> SearchResult:
        """Turn an answer from `_fetch_raw` into entries or suggestions."""
