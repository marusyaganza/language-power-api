# tests/api/test_app_settings.py
"""Settings that differ between local development and production."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

import main
from settings import Settings, settings
from tests.api.conftest import signup

pytestmark = pytest.mark.anyio

REPO_ROOT = Path(__file__).resolve().parents[2]
# What `_app_built_with` reports on. Only a test's own values count, never the shell's.
_DESCRIBED_SETTINGS = ("DOCS_ENABLED", "CORS_ORIGINS", "ROOT_PATH")


def _app_built_with(**env: str) -> dict:
    """Import `main` in a fresh interpreter with extra env vars; describe the app.

    The app reads these settings once, when `main` is imported, so they cannot
    be changed for an app that already exists. The interpreter starts in an
    empty directory, so a developer's `.env` (read from the working directory)
    isn't loaded, and the described settings are dropped from the inherited
    environment: without `env`, the app gets the real defaults.
    """
    script = (
        "import json, main\n"
        "print(json.dumps({\n"
        "    'docs': [main.app.docs_url, main.app.redoc_url, main.app.openapi_url],\n"
        "    'middleware': [m.cls.__name__ for m in main.app.user_middleware],\n"
        "    'root_path': main.app.root_path,\n"
        "}))\n"
    )
    inherited = {k: v for k, v in os.environ.items() if k not in _DESCRIBED_SETTINGS}
    with tempfile.TemporaryDirectory() as empty_dir:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=empty_dir,
            env={**inherited, "PYTHONPATH": str(REPO_ROOT), **env},
            capture_output=True,
            text=True,
            check=True,
        )
    return json.loads(result.stdout)


def test_production_settings_turn_off_docs_and_cors():
    app = _app_built_with(DOCS_ENABLED="false", CORS_ORIGINS="[]")
    assert app == {"docs": [None, None, None], "middleware": [], "root_path": ""}


def test_development_defaults_keep_docs_and_cors():
    app = _app_built_with()
    assert app == {
        "docs": ["/docs", "/redoc", "/openapi.json"],
        "middleware": ["CORSMiddleware"],
        "root_path": "",
    }


def test_the_demo_serves_its_docs_under_the_proxys_prefix():
    assert _app_built_with(ROOT_PATH="/api")["root_path"] == "/api"


@pytest.mark.parametrize("value", ["api", "/api/", "//api", "/api//v1"])
def test_root_path_must_be_a_clean_prefix(value):
    with pytest.raises(ValidationError):
        Settings(root_path=value, use_mocks=True)


# --------------------------------------------------------------------------- #
# Behind a proxy that strips /api (Netlify, the Vite dev proxy)
# --------------------------------------------------------------------------- #


@pytest.fixture
def behind_api_prefix(monkeypatch):
    monkeypatch.setattr(main.app, "root_path", "/api")


async def test_docs_load_the_schema_through_the_prefix(make_client, behind_api_prefix):
    client = make_client()
    docs = await client.get("/docs")
    assert docs.status_code == 200
    assert "'/api/openapi.json'" in docs.text

    schema = (await client.get("/openapi.json")).json()
    assert schema["servers"] == [{"url": "/api"}]  # where "Try it out" sends requests
    assert "/auth/config" in schema["paths"]


async def test_routes_answer_without_the_prefix_as_the_proxy_forwards_them(make_client, behind_api_prefix):
    client = make_client()
    await signup(client)
    assert (await client.get("/auth/me")).status_code == 200
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_the_schema_has_no_servers_without_a_prefix(make_client):
    schema = (await make_client().get("/openapi.json")).json()
    assert "servers" not in schema


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


async def test_the_docs_have_the_apps_own_title(make_client):
    info = (await make_client().get("/openapi.json")).json()["info"]
    assert (info["title"], info["version"]) == ("Language Power API", "3.0.0")
    assert "session cookie" in info["description"]
