from dictionary.base import DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry, unique_definitions
from dictionary.helpers.mw import (
    extract_audio,
    extract_definitions,
    extract_examples,
    extract_image,
    extract_image_desc,
    extract_transcription,
    fetch_entries,
    format_entries,
    format_name,
    is_suggestion_response,
)
from settings import settings
from words.language import Language

# Merriam-Webster's Collegiate Dictionary (MW API docs).
API_URL = "https://dictionaryapi.com/api/v3/references/collegiate/json"


class EnglishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> SearchResult:
        raw_items = await self._fetch_raw(query)

        if is_suggestion_response(raw_items):
            return SearchResult(suggestions=raw_items)

        return SearchResult(words=format_entries(raw_items, self._format))

    async def _fetch_raw(self, query: str) -> list:
        return await fetch_entries(API_URL, settings.english_api_key.get_secret_value(), query)

    def _format(self, word):
        meta = word["meta"]
        name = format_name(word)
        language = Language("en")
        uuid = meta["uuid"]
        stems = meta["stems"]
        fl = word.get("fl", "")  # cross-reference entries have none
        defs = unique_definitions(extract_definitions(word))
        audio_url = extract_audio(word, language, "us")
        transcription = extract_transcription(word)
        examples = extract_examples(word)
        img_url = extract_image(word)
        img_desc = extract_image_desc(word)

        return DictionaryEntry(
            uuid=uuid,
            name=name,
            language=language,
            fl=fl,
            stems=stems,
            defs=defs,
            audio_url=audio_url,
            transcription=transcription,
            img_url=img_url,
            img_desc=img_desc,
            examples=examples,
        )
