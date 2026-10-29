# tests/conftest.py
"""Test-wide setup. Loaded by pytest before any test module is imported."""

import os

# Tests never use the real Merriam-Webster API. This must run before any app
# import: `settings` and `PROVIDERS` are built once, at import time. Real
# environment variables take priority over `.env`, and assigning (rather than
# setdefault) overrides the shell too, so the real keys are never loaded,
# even though mock mode does not need keys. Tests also run without a `.env`.
os.environ.update(
    {
        "USE_MOCKS": "true",
        "SPANISH_API_KEY": "test-key-not-used",
        "ENGLISH_API_KEY": "test-key-not-used",
        # The app (and Alembic) only ever see the test database, so no test can
        # reach the dev data. tests/api/conftest.py recreates it on every run.
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+psycopg://app_user:dev_password@localhost:5432/language_app_test",
        ),
        # Redis database 15, which tests/api/conftest.py flushes after every test.
        # Set as a URL because the database number in a URL overrides a `db=`
        # argument, so passing db=15 next to the dev URL would flush the dev data.
        "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"),
        # Never report test errors to Sentry, even with a DSN in `.env`.
        "SENTRY_DSN": "",
        # URLs as the app builds them without a proxy, even with a ROOT_PATH in `.env`.
        "ROOT_PATH": "",
        # Tests read /docs and /openapi.json, even with DOCS_ENABLED=false in `.env`.
        "DOCS_ENABLED": "true",
    }
)

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
