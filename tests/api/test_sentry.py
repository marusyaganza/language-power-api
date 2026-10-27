# tests/api/test_sentry.py
"""What an error report sent to Sentry contains, end to end (core.sentry).

Sentry is started for real, with a transport that keeps events in a list
instead of sending them.
"""

import json

import httpx
import pytest
import sentry_sdk
from pydantic import SecretStr
from sentry_sdk.transport import Transport

from core.sentry import sentry_options
from settings import settings
from words import service as words_service

pytestmark = pytest.mark.anyio

MW_KEY = "the-real-mw-key"
SIGNATURE = "a.netlify.signature"
CLIENT_IP = "203.0.113.7"


@pytest.fixture
def sentry_events():
    events = []

    class KeepEvents(Transport):
        def capture_envelope(self, envelope):
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    options = sentry_options(
        settings.model_copy(
            update={
                "sentry_dsn": SecretStr("https://public@sentry.invalid/1"),
                "sentry_environment": "test",
                "sentry_release": "abc123",
            }
        )
    )
    sentry_sdk.init(**options, transport=KeepEvents())
    assert not sentry_sdk.get_client().should_send_default_pii()
    try:
        yield events
    finally:
        sentry_sdk.init()  # no DSN: nothing is reported after this test


async def test_an_error_report_holds_no_secrets_or_personal_data(client, sentry_events, monkeypatch):
    email = (await client.get("/auth/me")).json()["email"]
    session_id = client.cookies[settings.session_cookie_name]

    async def look_up_then_fail(db, user_id, payload):
        # Like a dictionary lookup: the key travels in the query string.
        mw = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
        async with mw:
            await mw.get("https://mw.invalid/json/casa", params={"key": MW_KEY})
        raise RuntimeError("saving failed")

    monkeypatch.setattr(words_service, "save_word", look_up_then_fail)
    with pytest.raises(RuntimeError):
        await client.post(
            "/words/save",
            json={"uuid": "u-1", "name": "palabrasecreta", "language": "es", "fl": "noun", "defs": ["x"]},
            headers={"X-Nf-Sign": SIGNATURE, "X-Nf-Client-Connection-Ip": CLIENT_IP, "User-Agent": "test-agent"},
        )

    [event] = [e for e in sentry_events if e.get("exception")]
    assert event["exception"]["values"][-1]["value"] == "saving failed"
    assert (event["environment"], event["release"]) == ("test", "abc123")

    sent = json.dumps(event)
    for secret in [MW_KEY, session_id, SIGNATURE, CLIENT_IP, email, "palabrasecreta"]:
        assert secret not in sent
    assert "session:" not in sent  # no Redis keys
    assert event["request"]["headers"]["user-agent"] == "test-agent"

    # The dictionary request is still in the breadcrumbs, only without its key.
    [lookup] = [c for c in event["breadcrumbs"]["values"] if "mw.invalid" in c.get("data", {}).get("url", "")]
    assert lookup["data"]["url"] == "https://mw.invalid/json/casa"
