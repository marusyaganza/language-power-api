from dictionary.en.en import EnglishDictionaryProvider
from dictionary.en.mock import MockEnglishDictionaryProvider
from dictionary.es.es import SpanishDictionaryProvider
from dictionary.es.mock import MockSpanishDictionaryProvider
from settings import settings


def build_providers():
    if settings.use_mocks:
        return {"en": MockEnglishDictionaryProvider(), "es": MockSpanishDictionaryProvider()}
    return {"en": EnglishDictionaryProvider(), "es": SpanishDictionaryProvider()}


PROVIDERS = build_providers()
