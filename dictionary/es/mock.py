from dictionary.es.es import SpanishDictionaryProvider
from dictionary.mock import MockDictionaryMixin
from words.language import Language


class MockSpanishDictionaryProvider(MockDictionaryMixin, SpanishDictionaryProvider):
    language = Language.ES
