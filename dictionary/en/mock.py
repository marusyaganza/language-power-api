from dictionary.en.en import EnglishDictionaryProvider
from dictionary.mock import MockDictionaryMixin
from words.language import Language


class MockEnglishDictionaryProvider(MockDictionaryMixin, EnglishDictionaryProvider):
    language = Language.EN
