from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from words.word import Word


@dataclass
class SearchResult:
    """A dictionary lookup: entries, or spelling suggestions when nothing matched.

    `mock_queries` is set only by the mock providers, for a query that has no
    fixture: the queries that do.
    """

    words: list[Word] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    mock_queries: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.words)

    @property
    def is_empty(self) -> bool:
        return not (self.words or self.suggestions or self.mock_queries)


class DictionaryProvider(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> SearchResult:
        """Look `query` up and return the entries or suggestions."""