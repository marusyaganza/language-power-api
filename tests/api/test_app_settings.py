# tests/api/test_app_settings.py
"""Settings that differ between local development and production."""

import json
import os
import subprocess
import sys

import pytest

from settings import settings
from tests.api.conftest import signup

pytestmark = pytest.mark.anyio


def _app_built_with(**env: str) -> dict:
    """Import `main` in a fresh interpreter with extra env vars; describe the app.

    The app reads these settings once, when `main` is imported, so they cannot
    be changed for an app that already exists.
    """
    script = (
        "import json, main\n"
        "print(json.dumps({\n"
        "    'docs': [main.app.docs_url, main.app.redoc_url, main.app.openapi_url],\n"
        "    'middleware': [m.cls.__name__ for m in main.app.user_middleware],\n"
        "}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_production_settings_turn_off_docs_and_cors():
    app = _app_built_with(DOCS_ENABLED="false", CORS_ORIGINS="[]")
    assert app == {"docs": [None, None, None], "middleware": []}


def test_development_defaults_keep_docs_and_cors():
    app = _app_built_with()
    assert app == {
        "docs": ["/docs", "/redoc", "/openapi.json"],
        "middleware": ["CORSMiddleware"],
    }


async def test_session_cookie_is_secure_when_configured(make_client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    client = make_client()
    response = await client.post(
        "/auth/signup", json={"email": "secure@example.com", "password": "correct-horse-battery"}
    )
    assert response.status_code == 201
    assert "secure" in response.headers["set-cookie"].lower().split("; ")


async def test_session_cookie_is_not_secure_by_default(make_client):
    client = make_client()
    await signup(client)
    assert (await client.get("/auth/me")).status_code == 200
