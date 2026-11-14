# tests/api/test_image_settings.py
"""Image search is off by default and can't be turned on for the public demo."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from settings import Settings, settings

pytestmark = pytest.mark.anyio

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
SETTINGS_ENV = (
    "AUDIO_ENGINES",
    "IMAGE_SEARCH_PROVIDERS",
    "PIXABAY_API_KEY",
    "IMAGE_SAFE_SEARCH",
    "MEDIA_BUCKET",
    "SIGNUP_ENABLED",
    "USE_MOCKS",
)
PIXABAY_ON = {"IMAGE_SEARCH_PROVIDERS": '["pixabay"]', "PIXABAY_API_KEY": "some-key", "MEDIA_BUCKET": "some-bucket"}


def settings_from(env: dict[str, str], monkeypatch) -> Settings:
    """Settings built from these env vars only (no `.env` file), as Cloud Run would."""
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def deploy_env(name: str) -> dict[str, str]:
    return yaml.safe_load((DEPLOY / name).read_text(encoding="utf-8"))


def test_image_search_is_off_by_default_with_safe_search(monkeypatch):
    built = settings_from({"USE_MOCKS": "false"}, monkeypatch)

    assert (built.image_search_providers, built.image_safe_search) == ([], True)


@pytest.mark.parametrize("value", ["", "  ", "[]"])
def test_an_empty_setting_means_off(monkeypatch, value):
    env = {"USE_MOCKS": "false", "IMAGE_SEARCH_PROVIDERS": value}

    assert settings_from(env, monkeypatch).image_search_providers == []


def test_a_setting_that_isnt_json_is_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        settings_from({"USE_MOCKS": "true", "IMAGE_SEARCH_PROVIDERS": "pixabay"}, monkeypatch)


def test_an_unknown_source_is_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        settings_from({"USE_MOCKS": "true", "IMAGE_SEARCH_PROVIDERS": '["unsplash"]'}, monkeypatch)


def test_the_demo_refuses_to_start_with_image_search_on(monkeypatch):
    with pytest.raises(ValidationError, match="private deployments only: turn off IMAGE_SEARCH_PROVIDERS"):
        settings_from(deploy_env("demo.env.yaml") | PIXABAY_ON, monkeypatch)


def test_the_refusal_names_every_media_feature_on(monkeypatch):
    env = deploy_env("demo.env.yaml") | PIXABAY_ON | {"AUDIO_ENGINES": '["google"]'}

    with pytest.raises(ValidationError, match="turn off AUDIO_ENGINES and IMAGE_SEARCH_PROVIDERS or SIGNUP_ENABLED"):
        settings_from(env, monkeypatch)


def test_the_personal_deployment_can_turn_image_search_on(monkeypatch):
    env = deploy_env("personal.env.yaml") | PIXABAY_ON | {"IMAGE_SAFE_SEARCH": "false"}
    built = settings_from(env, monkeypatch)

    assert (built.image_search_providers, built.image_safe_search) == (["pixabay"], False)


def test_real_image_search_needs_a_bucket(monkeypatch):
    env = {"USE_MOCKS": "false", "SIGNUP_ENABLED": "false"} | PIXABAY_ON
    del env["MEDIA_BUCKET"]

    with pytest.raises(ValidationError, match="MEDIA_BUCKET must be set when IMAGE_SEARCH_PROVIDERS is on"):
        settings_from(env, monkeypatch)


def test_real_pixabay_search_needs_its_key(monkeypatch):
    env = {"USE_MOCKS": "false", "SIGNUP_ENABLED": "false"} | PIXABAY_ON
    del env["PIXABAY_API_KEY"]

    with pytest.raises(ValidationError, match="PIXABAY_API_KEY"):
        settings_from(env, monkeypatch)


def test_audio_alone_needs_no_pixabay_key(monkeypatch):
    env = deploy_env("personal.env.yaml") | {"AUDIO_ENGINES": '["google"]', "MEDIA_BUCKET": "some-bucket"}

    assert settings_from(env, monkeypatch).pixabay_api_key is None


def test_mocks_allow_image_search_with_signup_on_no_bucket_and_no_key(monkeypatch):
    env = {"USE_MOCKS": "true", "SIGNUP_ENABLED": "true", "IMAGE_SEARCH_PROVIDERS": '["pixabay"]'}

    assert settings_from(env, monkeypatch).image_search_providers == ["pixabay"]


async def test_the_config_says_image_search_is_off_by_default(make_client):
    assert (await make_client().get("/auth/config")).json()["image_search"] is False


async def test_the_config_says_image_search_is_on(make_client, monkeypatch):
    monkeypatch.setattr(settings, "image_search_providers", ["pixabay"])

    assert (await make_client().get("/auth/config")).json()["image_search"] is True
