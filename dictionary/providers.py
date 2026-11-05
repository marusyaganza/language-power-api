from dictionary.en.en import EnglishDictionaryProvider
from dictionary.en.mock import MockEnglishDictionaryProvider
from dictionary.es.es import SpanishDictionaryProvider
from dictionary.es.mock import MockSpanishDictionaryProvider
from dictionary.ko.ko import KoreanDictionaryProvider
from dictionary.ko.mock import MockKoreanDictionaryProvider
from settings import settings


def build_providers():
    if settings.use_mocks:
        return {
            "en": MockEnglishDictionaryProvider(),
            "es": MockSpanishDictionaryProvider(),
            "ko": MockKoreanDictionaryProvider(),
        }
    return {"en": EnglishDictionaryProvider(), "es": SpanishDictionaryProvider(), "ko": KoreanDictionaryProvider()}


PROVIDERS = build_providers()
