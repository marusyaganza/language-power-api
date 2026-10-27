from dictionary.base import DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry, unique_definitions
from dictionary.helpers.mw import (
    extract_audio,
    extract_definitions,
    extract_examples,
    extract_gender,
    extract_image,
    extract_image_desc,
    fetch_entries,
    format_entries,
    format_name,
    is_suggestion_response,
)
from settings import settings
from words.language import Language

# Merriam-Webster's Spanish-English Dictionary (MW API docs).
API_URL = "https://www.dictionaryapi.com/api/v3/references/spanish/json"


class SpanishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> SearchResult:
        raw_items = await self._fetch_raw(query)
        if is_suggestion_response(raw_items):
            return SearchResult(suggestions=raw_items)
        return SearchResult(words=format_entries(raw_items, self._format))

    async def _fetch_raw(self, query: str) -> list:
        return await fetch_entries(API_URL, settings.spanish_api_key.get_secret_value(), query)

    def _format(self, word):
        meta = word["meta"]
        name = format_name(word)
        language = Language("es")
        uuid = meta["uuid"]
        stems = meta["stems"]
        fl = word.get("fl", "")  # cross-reference entries have none
        defs = unique_definitions(extract_definitions(word))
        audio_url = extract_audio(word, language, "me")
        examples = extract_examples(word)
        img_url = extract_image(word)
        img_desc = extract_image_desc(word)
        gender = extract_gender(fl)

        return DictionaryEntry(
            uuid=uuid,
            name=name,
            language=language,
            fl=fl,
            stems=stems,
            defs=defs,
            audio_url=audio_url,
            img_url=img_url,
            img_desc=img_desc,
            examples=examples,
            gender=gender,
        )
