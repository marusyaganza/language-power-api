from dictionary.en.en import EnglishDictionaryProvider
from dictionary.en.mock import MockEnglishDictionaryProvider
from dictionary.es.es import SpanishDictionaryProvider
from dictionary.es.mock import MockSpanishDictionaryProvider
from dictionary.ko.ko import KoreanDictionaryProvider
from dictionary.ko.mock import MockKoreanDictionaryProvider
from settings import settings


def build_providers():
    """A provider for each language the deployment offers (`settings.enabled_languages`)."""
    if settings.use_mocks:
        providers = {
            "en": MockEnglishDictionaryProvider,
            "es": MockSpanishDictionaryProvider,
            "ko": MockKoreanDictionaryProvider,
        }
    else:
        providers = {"en": EnglishDictionaryProvider, "es": SpanishDictionaryProvider, "ko": KoreanDictionaryProvider}
    return {language: provider() for language, provider in providers.items() if language in settings.enabled_languages}


PROVIDERS = build_providers()
