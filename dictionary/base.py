from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from dictionary.entry import DictionaryEntry


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
    @abstractmethod
    async def fetch(self, query: str) -> SearchResult:
        """Look `query` up and return the entries or suggestions.

        Raises:
            DictionaryError: the dictionary is unreachable, timed out, or
                answered with an error or an unexpected response.
        """