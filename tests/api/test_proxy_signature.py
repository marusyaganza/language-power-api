# tests/api/test_proxy_signature.py
"""Only requests signed by the frontend's Netlify proxy reach the API (core.proxy_signature)."""

import time

import jwt
import pytest
from pydantic import SecretStr

from settings import settings
from tests.api.conftest import signup

pytestmark = pytest.mark.anyio

# At least 32 bytes, the minimum PyJWT recommends for HS256 (it warns otherwise).
SECRET = "test-proxy-secret-test-proxy-secret"
REJECTED = {"detail": "Request did not come through the frontend proxy"}


def sign(claims: dict | None = None, secret: str = SECRET) -> str:
    """A token like the one Netlify puts in X-Nf-Sign."""
    payload = {"iss": "netlify", "deploy_context": "production", **(claims or {})}
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(settings, "proxy_signature_secret", SecretStr(SECRET))


async def test_unsigned_request_is_rejected(make_client, enforced):
    response = await make_client().get("/auth/config")
    assert response.status_code == 403
    assert response.json() == REJECTED


async def test_signed_request_passes(make_client, enforced):
    response = await make_client().get("/auth/config", headers={"X-Nf-Sign": sign()})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        sign(secret="another-secret-another-secret-another"),
        sign({"iss": "someone-else"}),
        jwt.encode({"deploy_context": "production"}, SECRET, algorithm="HS256"),  # no issuer
        sign({"exp": int(time.time()) - 60}),
        jwt.encode({"iss": "netlify"}, None, algorithm="none"),  # unsigned token
        "not-a-token",
    ],
    ids=["wrong-secret", "wrong-issuer", "no-issuer", "expired", "alg-none", "garbage"],
)
async def test_invalid_signature_is_rejected(make_client, enforced, token):
    response = await make_client().get("/auth/config", headers={"X-Nf-Sign": token})
    assert response.status_code == 403
    assert response.json() == REJECTED


async def test_a_valid_session_doesnt_replace_the_signature(make_client, enforced):
    client = make_client()
    client.headers["X-Nf-Sign"] = sign()
    await signup(client)
    assert (await client.get("/auth/me")).status_code == 200

    del client.headers["X-Nf-Sign"]
    response = await client.get("/auth/me")
    assert response.status_code == 403
    assert response.json() == REJECTED


async def test_health_needs_no_signature(make_client, enforced):
    response = await make_client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_nothing_is_checked_without_a_secret(make_client):
    assert settings.proxy_signature_secret is None
    assert (await make_client().get("/auth/config")).status_code == 200
