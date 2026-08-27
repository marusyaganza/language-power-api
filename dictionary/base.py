from abc import ABC, abstractmethod
from words.word import Word

class DictionaryProvider(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> list[Word]:
        """Fetch translation/word data and return Word instances."""