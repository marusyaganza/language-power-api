# tests/conftest.py
"""Test-wide setup. Loaded by pytest before any test module is imported."""
import os

# Tests never use the real Merriam-Webster API. This must run before any app
# import: `settings` and `PROVIDERS` are built once, at import time. Real
# environment variables take priority over `.env`, and assigning (rather than
# setdefault) overrides the shell too, so the real keys are never loaded.
# `.invalid` never resolves, so a request that slips through fails at once.
# With every required setting given here, tests also run without a `.env`.
os.environ.update({
    "USE_MOCKS": "True",
    "SPANISH_API_KEY": "test-key-not-used",
    "ENGLISH_API_KEY": "test-key-not-used",
    "SPANISH_API_URL": "https://mw-api.invalid",
    "ENGLISH_API_URL": "https://mw-api.invalid",
    "AUDIO_ENDPOINT": "https://mw-media.invalid/audio",
    "IMG_ENDPOINT": "https://mw-media.invalid/img",
    # The app (and Alembic) only ever see the test database, so no test can
    # reach the dev data. tests/api/conftest.py recreates it on every run.
    "DATABASE_URL": os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://app_user:dev_password@localhost:5432/language_app_test",
    ),
})

from dictionary.en.mock import MockEnglishDictionaryProvider  # noqa: E402
from dictionary.es.mock import MockSpanishDictionaryProvider  # noqa: E402
from dictionary.providers import PROVIDERS  # noqa: E402

# Stop the whole run if the override did not take effect, instead of letting
# tests pass against the real dictionaries.
if not (
    isinstance(PROVIDERS["en"], MockEnglishDictionaryProvider)
    and isinstance(PROVIDERS["es"], MockSpanishDictionaryProvider)
):
    raise RuntimeError(f"Tests must use mock dictionary providers, got {PROVIDERS}")
