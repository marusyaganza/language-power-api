# tests/api/test_ip_limits.py
"""Per-IP limits on requests, signups and logins, where Netlify tells us the IP.

The IP is only trusted behind the proxy signature (core.proxy_signature.client_ip),
so every test here turns the signature check on and signs its requests.
"""

import pytest
from pydantic import SecretStr

import auth.dependencies
import auth.service
from auth.rate_limit import AttemptLimiter
from settings import settings
from tests.api.conftest import PASSWORD, signup
from tests.api.test_proxy_signature import SECRET, sign

pytestmark = pytest.mark.anyio

IP = "203.0.113.7"
OTHER_IP = "198.51.100.20"


@pytest.fixture
def from_ip(make_client, monkeypatch):
    """A factory for signed clients that come from `ip`."""
    monkeypatch.setattr(settings, "proxy_signature_secret", SecretStr(SECRET))

    def _make(ip: str = IP):
        client = make_client()
        client.headers.update({"X-Nf-Sign": sign(), "X-Nf-Client-Connection-Ip": ip})
        return client

    return _make


def limit(monkeypatch, name, attempts, module=auth.service):
    monkeypatch.setattr(module, name, AttemptLimiter(attempts, 3600))


async def login(client, email, password=PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def signup_as(client, email):
    return await client.post("/auth/signup", json={"email": email, "password": PASSWORD})


# --------------------------------------------------------------------------- #
# Every request
# --------------------------------------------------------------------------- #


async def test_requests_are_limited_per_ip(from_ip, monkeypatch):
    limit(monkeypatch, "_request_limiter", 3, module=auth.dependencies)
    client = from_ip()
    for _ in range(3):
        assert (await client.get("/auth/config")).status_code == 200

    refused = await client.get("/auth/config")
    assert refused.status_code == 429
    assert refused.json() == {"detail": "Too many requests, try again later"}
    assert 0 < int(refused.headers["retry-after"]) <= 3600

    assert (await from_ip(OTHER_IP).get("/auth/config")).status_code == 200


async def test_the_request_limit_comes_before_the_session_lookup(from_ip, monkeypatch):
    client = from_ip()
    await signup(client)
    limit(monkeypatch, "_request_limiter", 1, module=auth.dependencies)
    assert (await client.get("/auth/me")).status_code == 200

    async def must_not_run(session_id):
        raise AssertionError("looked up the session of a refused request")

    monkeypatch.setattr(auth.service, "get_user_id_for_session", must_not_run)
    assert (await client.get("/auth/me")).status_code == 429


async def test_unsigned_requests_dont_use_up_the_ips_requests(from_ip, make_client, monkeypatch):
    limit(monkeypatch, "_request_limiter", 1, module=auth.dependencies)
    forged = make_client()
    forged.headers["X-Nf-Client-Connection-Ip"] = IP
    assert (await forged.get("/auth/config")).status_code == 403

    assert (await from_ip().get("/auth/config")).status_code == 200


async def test_health_isnt_limited(from_ip, monkeypatch):
    limit(monkeypatch, "_request_limiter", 1, module=auth.dependencies)
    client = from_ip()
    for _ in range(3):
        assert (await client.get("/health")).status_code == 200
    assert (await client.get("/auth/config")).status_code == 200


async def test_nothing_is_limited_per_ip_without_the_signature_check(make_client, monkeypatch):
    limit(monkeypatch, "_request_limiter", 1, module=auth.dependencies)
    limit(monkeypatch, "_signup_ip_limiter", 1)
    limit(monkeypatch, "_login_ip_limiter", 1)
    client = make_client()
    client.headers["X-Nf-Client-Connection-Ip"] = IP
    user = await signup(client)
    second = make_client()
    second.headers["X-Nf-Client-Connection-Ip"] = IP
    await signup(second)
    for _ in range(2):
        assert (await login(client, user["email"])).status_code == 200
    assert (await client.get("/auth/me")).status_code == 200


# --------------------------------------------------------------------------- #
# Signups
# --------------------------------------------------------------------------- #


async def test_signups_are_limited_per_ip(from_ip, monkeypatch):
    limit(monkeypatch, "_signup_ip_limiter", 2)
    await signup(from_ip())
    await signup(from_ip())

    refused = await signup_as(from_ip(), "third@example.com")
    assert refused.status_code == 429
    assert refused.json() == {"detail": "Too many attempts, try again later"}
    assert int(refused.headers["retry-after"]) > 0

    await signup(from_ip(OTHER_IP))


async def test_an_ips_refused_signups_dont_use_up_everyones(from_ip, monkeypatch):
    limit(monkeypatch, "_signup_ip_limiter", 1)
    limit(monkeypatch, "_signup_limiter", 2)
    await signup(from_ip())
    for _ in range(3):
        assert (await signup_as(from_ip(), "more@example.com")).status_code == 429

    await signup(from_ip(OTHER_IP))


# --------------------------------------------------------------------------- #
# Logins
# --------------------------------------------------------------------------- #


async def test_an_emails_logins_are_counted_per_ip(from_ip):
    user = await signup(from_ip())
    attacker = from_ip(OTHER_IP)
    for _ in range(settings.login_attempt_limit):
        assert (await login(attacker, user["email"], "wrong-password")).status_code == 401
    assert (await login(attacker, user["email"])).status_code == 429

    # The owner, elsewhere, isn't locked out.
    assert (await login(from_ip(), user["email"])).status_code == 200


async def test_logins_are_limited_per_ip_across_emails(from_ip, monkeypatch):
    limit(monkeypatch, "_login_ip_limiter", 3)
    user = await signup(from_ip(OTHER_IP))
    client = from_ip()
    for n in range(3):
        assert (await login(client, f"guess-{n}@example.com")).status_code == 401

    refused = await login(client, user["email"])
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0

    assert (await login(from_ip(OTHER_IP), user["email"])).status_code == 200


async def test_a_successful_login_starts_the_ip_and_email_count_over(from_ip):
    client = from_ip()
    user = await signup(client)
    for _ in range(2):
        for _ in range(settings.login_attempt_limit - 1):
            assert (await login(client, user["email"], "wrong-password")).status_code == 401
        assert (await login(client, user["email"])).status_code == 200
