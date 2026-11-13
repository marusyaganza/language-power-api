# tests/api/test_audio_settings.py
"""Audio generation is off by default and can't be turned on for the public demo."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from settings import Settings, settings

pytestmark = pytest.mark.anyio

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"


def settings_from(env: dict[str, str], monkeypatch) -> Settings:
    """Settings built from these env vars only (no `.env` file), as Cloud Run would."""
    for name in ("AUDIO_ENGINES", "MEDIA_BUCKET", "SIGNUP_ENABLED", "USE_MOCKS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def deploy_env(name: str) -> dict[str, str]:
    return yaml.safe_load((DEPLOY / name).read_text(encoding="utf-8"))


def test_audio_is_off_by_default(monkeypatch):
    assert settings_from({"USE_MOCKS": "false"}, monkeypatch).audio_engines == []


@pytest.mark.parametrize("value", ["", "  ", "[]"])
def test_an_empty_setting_means_off(monkeypatch, value):
    assert settings_from({"USE_MOCKS": "false", "AUDIO_ENGINES": value}, monkeypatch).audio_engines == []


def test_a_setting_that_isnt_json_is_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        settings_from({"USE_MOCKS": "true", "AUDIO_ENGINES": "google"}, monkeypatch)


def test_the_demo_refuses_to_start_with_audio_on(monkeypatch):
    env = deploy_env("demo.env.yaml") | {"AUDIO_ENGINES": '["google"]', "MEDIA_BUCKET": "some-bucket"}

    with pytest.raises(ValidationError, match="private deployments only"):
        settings_from(env, monkeypatch)


def test_the_demo_starts_as_it_is(monkeypatch):
    assert settings_from(deploy_env("demo.env.yaml"), monkeypatch).audio_engines == []


def test_the_personal_deployment_can_turn_audio_on(monkeypatch):
    env = deploy_env("personal.env.yaml") | {"AUDIO_ENGINES": '["google"]', "MEDIA_BUCKET": "some-bucket"}

    assert settings_from(env, monkeypatch).audio_engines == ["google"]


def test_the_personal_deployment_starts_with_audio_on_as_it_is(monkeypatch):
    settings = settings_from(deploy_env("personal.env.yaml"), monkeypatch)

    assert (settings.audio_engines, settings.media_bucket) == (["google"], "py-lp-512416-media")


def test_real_audio_needs_a_bucket(monkeypatch):
    env = {k: v for k, v in deploy_env("personal.env.yaml").items() if k != "MEDIA_BUCKET"}

    with pytest.raises(ValidationError, match="MEDIA_BUCKET"):
        settings_from(env, monkeypatch)


def test_mocks_allow_audio_with_signup_on_and_no_bucket(monkeypatch):
    env = {"USE_MOCKS": "true", "SIGNUP_ENABLED": "true", "AUDIO_ENGINES": '["google"]'}

    assert settings_from(env, monkeypatch).audio_engines == ["google"]


def test_an_unknown_engine_is_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        settings_from({"USE_MOCKS": "true", "AUDIO_ENGINES": '["gtts"]'}, monkeypatch)


async def test_the_config_has_no_audio_engines_by_default(make_client):
    assert (await make_client().get("/auth/config")).json()["audio_engines"] == []


async def test_the_config_lists_the_audio_engines(make_client, monkeypatch):
    monkeypatch.setattr(settings, "audio_engines", ["google"])

    assert (await make_client().get("/auth/config")).json()["audio_engines"] == ["google"]


def test_the_audio_log_line_reaches_the_logs_and_library_chatter_doesnt():
    """One INFO line per generation is kept for comparing engines; Python drops INFO unless configured."""
    script = (
        "import logging, main\n"
        "logging.getLogger('audio.service').info('Audio generated: engine=google')\n"
        "logging.getLogger('httpx').info('HTTP Request: GET https://example.com')\n"
        "logging.getLogger('words.service').warning('Dictionary lookup failed')\n"
    )
    with tempfile.TemporaryDirectory() as empty_dir:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=empty_dir,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=True,
        )

    assert "Audio generated: engine=google" in result.stderr
    assert "Dictionary lookup failed" in result.stderr
    assert "HTTP Request" not in result.stderr
