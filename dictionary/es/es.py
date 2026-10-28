from core.language import Language
from dictionary.merriam_webster.api import extract_gender
from dictionary.merriam_webster.provider import MerriamWebsterProvider
from settings import settings

# Merriam-Webster's Spanish-English Dictionary (MW API docs). It has no
# illustrations (no `art`), so entries never have an image.
API_URL = "https://www.dictionaryapi.com/api/v3/references/spanish/json"


class SpanishDictionaryProvider(MerriamWebsterProvider):
    language = Language.ES
    api_url = API_URL
    audio_country = "me"

    def _api_key(self) -> str:
        return settings.spanish_api_key.get_secret_value()

    def _keep(self, raw_items: list) -> list:
        """Drop the English half of the bilingual dictionary.

        A search for an English word ("dog") returns English entries
        (`meta.lang` "en") translated into Spanish. They are not Spanish words,
        and their audio is not under the Spanish path. Entries with an
        unexpected shape are kept, so `format_entries` still reports them.
        """
        return [item for item in raw_items if _headword_language(item) in ("es", None)]

    def _extra_fields(self, entry: dict) -> dict:
        return {"gender": extract_gender(entry.get("fl", ""))}


def _headword_language(item) -> str | None:
    """The entry's `meta.lang` ("es" or "en"), or None if it has none."""
    meta = item.get("meta") if isinstance(item, dict) else None
    return meta.get("lang") if isinstance(meta, dict) else None
