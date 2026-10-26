from dictionary.helpers.mw import extract_examples
from words.language import Language
from dictionary.base import DictionaryProvider
from words.word import Word, unique_definitions
from dictionary.base import SearchResult
from settings import settings
from dictionary.helpers.mw import fetch_entries, format_entries, format_name, extract_audio, extract_image, extract_image_desc, extract_definitions, is_suggestion_response, extract_gender

# Merriam-Webster's Spanish-English Dictionary (MW API docs).
API_URL = 'https://www.dictionaryapi.com/api/v3/references/spanish/json'

class SpanishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> SearchResult:
       raw_items = await self._fetch_raw(query)
       if is_suggestion_response(raw_items):
        return SearchResult(suggestions=raw_items)
       return SearchResult(words=format_entries(raw_items, self._format))
    
    async def _fetch_raw(self, query: str) -> list:
        return await fetch_entries(API_URL, settings.spanish_api_key.get_secret_value(), query)
    
    def _format(self, word):
        meta = word['meta']
        name = format_name(meta['id'])
        language = Language('es')
        uuid = meta['uuid']
        stems =  meta['stems']
        fl = word.get('fl', '')  # cross-reference entries have none
        defs = unique_definitions(extract_definitions(word))
        audio_url = extract_audio(word, language, 'me')
        examples = extract_examples(word)
        img_url = extract_image(word)
        img_desc = extract_image_desc(word)
        gender = extract_gender(fl)

        return Word(name=name, language=language, uuid=uuid, stems=stems, fl=fl, defs=defs, audio_url = audio_url, examples = examples, gender = gender, img_url = img_url, img_desc = img_desc)