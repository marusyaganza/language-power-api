# tests/unit/test_enabled_language.py
"""`EnabledLanguage`: a request's language must be one the deployment offers."""

import pytest
from pydantic import TypeAdapter, ValidationError

from core.enabled_language import EnabledLanguage
from core.language import Language
from settings import settings

LANGUAGE = TypeAdapter(EnabledLanguage)


def test_an_offered_language_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "enabled_languages", [Language.EN, Language.ES])

    assert LANGUAGE.validate_python("es") is Language.ES


def test_a_language_not_offered_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "enabled_languages", [Language.EN, Language.ES])

    with pytest.raises(ValidationError, match="Language 'ko' isn't available"):
        LANGUAGE.validate_python("ko")


def test_an_unknown_language_is_rejected_as_before():
    with pytest.raises(ValidationError, match="Input should be"):
        LANGUAGE.validate_python("fr")
