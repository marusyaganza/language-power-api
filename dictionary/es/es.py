from word.language import Language
from dictionary.base import DictionaryProvider
from word.word import Word
import httpx
from settings import settings

class SpanishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> list[Word]:
        raw_items = await self._fetch_raw(query)
        return [self._format(item) for item in raw_items]
    
    async def _fetch_raw(self, query: str) -> list[Word]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.spanish_api_url}/{query}key={settings.spanish_api_key}")
            data = resp.json()
        return [self._format(item) for item in data]
    
    def _format(self, word):
        meta = word['meta']
        raw_name = meta['id']
        # removing any extra symbols from the string
        name = ''.join(c for c in raw_name if c.isalpha())
        language = Language('es')
        uuid = meta['uuid']
        stems =  meta['stems']
        fl = word['fl']
        defs = word.get('shortdef', [])
        countryCode = 'me'
        prs = word.get('hwi').get('prs')
        audio_url = ''
        audio = ''
        if prs:
            audio = prs[0].get('sound').get('audio')
# if audio begins with "bix", the subdirectory should be "bix",
# if audio begins with "gg", the subdirectory should be "gg",
# if audio begins with a number or punctuation (eg, "_"), the subdirectory should be "number",
        if audio:
            subdir = audio[0]
            if audio.startswith('gg'):
                subdir = 'gg'
            if audio.startswith('bix'):
                subdir = 'bix'
            if not subdir.isalpha():
                sibdir = 'number'
            audio_url = f'{settings.audio_endpoint}/{language}/{countryCode}/mp3/{subdir}/{audio}.mp3'

        return Word(name=name, language=language, uuid=uuid, stems=stems, fl=fl, defs=defs, audio_url = audio_url)

    # guineafo
    # pussywil