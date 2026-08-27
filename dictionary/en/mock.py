# providers/mock.py
import json
from pathlib import Path
from words.language import Language
import asyncio
from dictionary.en.en import EnglishDictionaryProvider

class MockEnglishDictionaryProvider(EnglishDictionaryProvider):
    def __init__(self):
        self.language = Language('en')
        self._fixtures_dir = Path(__file__).parent.parent / "fixtures"

    async def _fetch_raw(self, query: str):
        file_path = self._fixtures_dir / self.language / f"{query}.json"
        if not file_path.exists():
            return []
        data = json.loads(file_path.read_text())
        return data
    
    

if __name__ == "__main__":
    async def main():
        provider = MockEnglishDictionaryProvider()
        result = await provider.fetch('fowl')
        for item in result:
            print(item)

    asyncio.run(main())