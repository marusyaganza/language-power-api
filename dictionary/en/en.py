from core.language import Language
from dictionary.merriam_webster.api import extract_image, extract_image_desc, extract_transcription
from dictionary.merriam_webster.provider import MerriamWebsterProvider
from settings import settings

# Merriam-Webster's Collegiate Dictionary (MW API docs).
API_URL = "https://dictionaryapi.com/api/v3/references/collegiate/json"


class EnglishDictionaryProvider(MerriamWebsterProvider):
    language = Language.EN
    api_url = API_URL
    audio_country = "us"

    def _api_key(self) -> str:
        return settings.english_api_key.get_secret_value()

    def _extra_fields(self, entry: dict) -> dict:
        return {
            "transcription": extract_transcription(entry),
            "img_url": extract_image(entry),
            "img_desc": extract_image_desc(entry),
        }
