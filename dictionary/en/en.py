import httpx
from words.language import Language
from dictionary.base import DictionaryProvider
from dictionary.helpers.mw import extract_examples, extract_audio, extract_transcription, format_name, is_suggestion_response
from words.word import Word
from dictionary.base import SearchResult
from settings import settings

class EnglishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> list[Word]:
        raw_items = await self._fetch_raw(query)

        if is_suggestion_response(raw_items):
            return SearchResult(suggestions=raw_items)

        return SearchResult(words=[self._format(item) for item in raw_items])
    
    async def _fetch_raw(self, query: str) -> list[Word]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.english_api_url}/{query}?key={settings.english_api_key}")
            data = resp.json()
        return data
    
    def _format(self, word):
        meta = word['meta']
        name = format_name(meta['id'])
        language = Language('en')
        uuid = meta['uuid']
        stems =  meta['stems']
        fl = word['fl']
        defs = word.get('shortdef', [])
        audio_url = extract_audio(word, language, 'us')
        transcription = extract_transcription(word)
        examples = extract_examples(word)

        return Word(name=name, language=language, uuid=uuid, stems=stems, fl=fl, defs=defs, audio_url = audio_url, transcription = transcription, examples = examples)



    


    