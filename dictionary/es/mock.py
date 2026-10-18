import asyncio

from dictionary.es.es import SpanishDictionaryProvider
from dictionary.mock import MockDictionaryMixin
from words.language import Language


class MockSpanishDictionaryProvider(MockDictionaryMixin, SpanishDictionaryProvider):
    language = Language.ES


if __name__ == "__main__":
    result = asyncio.run(MockSpanishDictionaryProvider().fetch("tener"))
    for word in result.words:
        print(word)
