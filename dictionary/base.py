from abc import ABC, abstractmethod
from word.word import Word

class DictionaryProvider(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> list[Word]:
        """Fetch translation/word data and return Word instances."""