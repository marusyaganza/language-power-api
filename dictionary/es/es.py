from dictionary.helpers.mw import extract_examples
from words.language import Language
from dictionary.base import DictionaryProvider
from words.word import Word
import httpx
from settings import settings
from dictionary.helpers.mw import format_name, extract_audio

class SpanishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> list[Word]:
        raw_items = await self._fetch_raw(query)
        return [self._format(item) for item in raw_items]
    
    async def _fetch_raw(self, query: str) -> list[Word]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.spanish_api_url}/{query}?key={settings.spanish_api_key}")
            data = resp.json()
        return data
    
    def _format(self, word):
        meta = word['meta']
        name = format_name(meta['id'])
        language = Language('es')
        uuid = meta['uuid']
        stems =  meta['stems']
        fl = word['fl']
        defs = word.get('shortdef', [])
        audio_url = extract_audio(word, language, 'me')
        examples = extract_examples(word)
        return Word(name=name, language=language, uuid=uuid, stems=stems, fl=fl, defs=defs, audio_url = audio_url, examples = examples)