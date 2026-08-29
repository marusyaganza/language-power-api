from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from words.word import Word

class DictionaryProvider(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> list[Word]:
        """Fetch translation/word data and return Word instances."""



@dataclass
class SearchResult:
    words: list[Word] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.words)