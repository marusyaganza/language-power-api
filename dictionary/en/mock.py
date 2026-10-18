import asyncio

from dictionary.en.en import EnglishDictionaryProvider
from dictionary.mock import MockDictionaryMixin
from words.language import Language


class MockEnglishDictionaryProvider(MockDictionaryMixin, EnglishDictionaryProvider):
    language = Language.EN


if __name__ == "__main__":
    result = asyncio.run(MockEnglishDictionaryProvider().fetch("fowl"))
    for word in result.words:
        print(word)
