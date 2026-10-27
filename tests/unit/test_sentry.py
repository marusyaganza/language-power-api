# tests/unit/test_sentry.py
from pydantic import SecretStr
from sentry_sdk.integrations.redis import RedisIntegration

from core.sentry import scrub_breadcrumb, scrub_event, sentry_options
from settings import settings


def with_sentry(**fields):
    return settings.model_copy(update={"sentry_dsn": SecretStr("https://public@sentry.invalid/1"), **fields})


def test_sentry_is_off_without_a_dsn():
    assert sentry_options(settings.model_copy(update={"sentry_dsn": None})) is None
    assert sentry_options(settings.model_copy(update={"sentry_dsn": SecretStr("")})) is None


def test_options_keep_personal_data_out():
    options = sentry_options(with_sentry(sentry_environment="personal", sentry_release="abc123"))
    # Left at its default (off): passing it is deprecated in favour of `data_collection`.
    assert "send_default_pii" not in options
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    assert any(isinstance(i, RedisIntegration) for i in options["disabled_integrations"])
    assert (options["environment"], options["release"]) == ("personal", "abc123")


def test_an_empty_release_is_no_release():
    # A local `docker build` without GIT_SHA sets SENTRY_RELEASE to "".
    assert sentry_options(with_sentry(sentry_release=""))["release"] is None


def test_only_harmless_request_headers_are_kept():
    event = {
        "request": {
            "headers": {
                "User-Agent": "Mozilla/5.0",
                "content-type": "application/json",
                "x-nf-sign": "a.signed.token",
                "x-nf-client-connection-ip": "203.0.113.7",
                "x-nf-geo": "eyJjaXR5Ijoi...",
                "Cookie": "session_id=secret",
            }
        }
    }
    assert scrub_event(event, {})["request"]["headers"] == {
        "User-Agent": "Mozilla/5.0",
        "content-type": "application/json",
    }


def test_an_event_without_a_request_is_unchanged():
    event = {"message": "something failed"}
    assert scrub_event(event, {}) == {"message": "something failed"}


def test_the_query_string_of_an_outgoing_request_is_dropped():
    crumb = {
        "category": "httplib",
        "data": {
            "url": "https://www.dictionaryapi.com/api/v3/references/spanish/json/casa",
            "http.query": "key=the-mw-key",
            "http.method": "GET",
        },
    }
    assert scrub_breadcrumb(crumb, {})["data"] == {
        "url": "https://www.dictionaryapi.com/api/v3/references/spanish/json/casa",
        "http.method": "GET",
    }
