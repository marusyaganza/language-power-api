from dictionary.base import DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry, unique_definitions
from dictionary.helpers.mw import (
    extract_audio,
    extract_definitions,
    extract_examples,
    extract_gender,
    fetch_entries,
    format_entries,
    format_name,
    is_suggestion_response,
)
from settings import settings
from words.language import Language

# Merriam-Webster's Spanish-English Dictionary (MW API docs). It has no
# illustrations (no `art`), so entries never have an image.
API_URL = "https://www.dictionaryapi.com/api/v3/references/spanish/json"


class SpanishDictionaryProvider(DictionaryProvider):
    async def fetch(self, query: str) -> SearchResult:
        raw_items = await self._fetch_raw(query)
        if is_suggestion_response(raw_items):
            return SearchResult(suggestions=raw_items)
        return SearchResult(words=format_entries(_spanish_headwords(raw_items), self._format))

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
        gender = extract_gender(fl)

        return DictionaryEntry(
            uuid=uuid,
            name=name,
            language=language,
            fl=fl,
            stems=stems,
            defs=defs,
            audio_url=audio_url,
            examples=examples,
            gender=gender,
        )


def _spanish_headwords(raw_items: list) -> list:
    """Drop the English half of the bilingual dictionary.

    A search for an English word ("dog") returns English entries
    (`meta.lang` "en") translated into Spanish. They are not Spanish words,
    and their audio is not under the Spanish path. Entries with an unexpected
    shape are kept, so `format_entries` still reports them.
    """
    return [item for item in raw_items if _headword_language(item) in ("es", None)]


def _headword_language(item) -> str | None:
    """The entry's `meta.lang` ("es" or "en"), or None if it has none."""
    meta = item.get("meta") if isinstance(item, dict) else None
    return meta.get("lang") if isinstance(meta, dict) else None
