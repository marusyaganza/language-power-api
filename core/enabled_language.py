"""The language of a request, which must be one this deployment offers (`settings.enabled_languages`).

Kept apart from `core.language`, which `settings` itself imports.
"""

from typing import Annotated

from pydantic import AfterValidator

from core.language import Language
from settings import settings


def _require_enabled(language: Language) -> Language:
    if language not in settings.enabled_languages:
        raise ValueError(f"Language {language.value!r} isn't available")
    return language


# For request fields and parameters: a language the deployment offers, or a 422.
EnabledLanguage = Annotated[Language, AfterValidator(_require_enabled)]
