# tests/api/test_demo_limits.py
"""The limits for a public deployment: searches, words, signups and account lifetime.

Each one is off unless its setting is set, which the tests here do one at a time.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from core import utc_day
from dictionary.providers import PROVIDERS
from settings import settings
from tests.api.conftest import PASSWORD, save_word, signup
from users.models import User

pytestmark = pytest.mark.anyio

# Queries with mock data, so a search that reaches the provider succeeds.
EN_QUERY = "heart"
ES_QUERY = "hola"


async def search(client, language="en", query=None):
    query = query or (EN_QUERY if language == "en" else ES_QUERY)
    return await client.get("/words/search", params={"query": query, "language": language})


@pytest.fixture
def lookups(monkeypatch):
    """Counts the calls that reach the English dictionary."""
    calls = []
    provider = PROVIDERS["en"]
    real_fetch = provider.fetch

    async def fetch(query):
        calls.append(query)
        return await real_fetch(query)

    monkeypatch.setattr(provider, "fetch", fetch)
    return calls


# --------------------------------------------------------------------------- #
# Searches
# --------------------------------------------------------------------------- #


async def test_searches_are_unlimited_by_default(client):
    response = await search(client)
    assert response.status_code == 200
    assert response.json()["searches_left"] is None
    limits = (await client.get("/words/search-limits")).json()
    assert limits == {"limit": None, "searches_left": {"en": None, "es": None}}


async def test_each_account_has_its_own_searches_per_language(client, make_client, monkeypatch, lookups):
    monkeypatch.setattr(settings, "searches_per_language", 2)

    assert [(await search(client)).json()["searches_left"] for _ in range(2)] == [1, 0]
    refused = await search(client)
    assert refused.status_code == 429
    assert refused.json()["detail"] == "You've used your 2 English searches in this demo"
    assert "retry-after" not in refused.headers
    assert len(lookups) == 2  # the refused search never reached the dictionary

    # Spanish has its own count, and so does another account.
    assert (await search(client, "es")).json()["searches_left"] == 1
    other = make_client()
    await signup(other)
    assert (await search(other)).status_code == 200

    limits = (await client.get("/words/search-limits")).json()
    assert limits == {"limit": 2, "searches_left": {"en": 0, "es": 1}}


async def test_a_search_with_no_results_still_counts(client, monkeypatch):
    monkeypatch.setattr(settings, "searches_per_language", 2)
    # A query without mock data returns the mock word list: the dictionary was asked.
    assert (await search(client, query="zzz")).json()["searches_left"] == 1


async def test_todays_searches_are_shared_by_everyone(client, make_client, monkeypatch, lookups):
    monkeypatch.setattr(settings, "daily_searches_per_language", 1)
    monkeypatch.setattr(settings, "searches_per_language", 5)
    assert (await search(client)).status_code == 200

    other = make_client()
    await signup(other)
    refused = await search(other)
    assert refused.status_code == 429
    assert refused.json()["detail"].startswith("The demo's dictionary budget for today is used up")
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 60 * 60
    assert len(lookups) == 1
    # The refused search didn't use one of the account's own searches either.
    assert (await other.get("/words/search-limits")).json()["searches_left"]["en"] == 5
    # Spanish is counted separately.
    assert (await search(other, "es")).status_code == 200


# --------------------------------------------------------------------------- #
# Saved words
# --------------------------------------------------------------------------- #


async def test_an_account_can_save_up_to_the_word_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "max_words_per_user", 2)
    await save_word(client, "casa")
    await save_word(client, "heart", language="en")
    response = await client.post("/words/save", json={"name": "perro", "language": "es", "fl": "noun", "defs": ["dog"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "You can save up to 2 words in this demo"


# --------------------------------------------------------------------------- #
# Signups per day
# --------------------------------------------------------------------------- #


async def test_signups_close_for_the_day_at_the_limit(make_client, monkeypatch):
    monkeypatch.setattr(settings, "daily_signup_limit", 1)
    client = make_client()
    assert (await client.get("/auth/config")).json()["signup_open_today"] is True
    await signup(client)

    assert (await client.get("/auth/config")).json()["signup_open_today"] is False
    refused = await make_client().post("/auth/signup", json={"email": "late@example.com", "password": PASSWORD})
    assert refused.status_code == 429
    assert refused.json()["detail"] == "Sorry, registration is closed for today, try again tomorrow"
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 60 * 60


async def test_the_days_signup_count_starts_from_the_database(client, make_client, monkeypatch):
    # `client` signed up before the limit was set, as if before a restart.
    monkeypatch.setattr(settings, "daily_signup_limit", 1)
    assert (await make_client().get("/auth/config")).json()["signup_open_today"] is False


async def test_signup_open_today_follows_signup_enabled(make_client, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    config = (await make_client().get("/auth/config")).json()
    assert config["signup_enabled"] is False
    assert config["signup_open_today"] is False


async def test_config_has_the_limits_for_the_demo_notice(make_client, monkeypatch):
    config = (await make_client().get("/auth/config")).json()
    assert config["account_ttl_hours"] is None
    assert config["searches_per_language"] is None

    monkeypatch.setattr(settings, "account_ttl_hours", 24)
    monkeypatch.setattr(settings, "searches_per_language", 10)
    config = (await make_client().get("/auth/config")).json()
    assert config["account_ttl_hours"] == 24
    assert config["searches_per_language"] == 10


# --------------------------------------------------------------------------- #
# Account lifetime
# --------------------------------------------------------------------------- #


async def _age_account(db, user_id: int, hours: int) -> None:
    await db.execute(update(User).where(User.id == user_id).values(created_at=utc_day.now() - timedelta(hours=hours)))


async def test_an_expired_account_is_logged_out_and_cannot_log_in(make_client, db, monkeypatch):
    monkeypatch.setattr(settings, "account_ttl_hours", 24)
    client = make_client()
    user = await signup(client)
    assert (await client.get("/auth/me")).status_code == 200

    await _age_account(db, user["id"], 25)
    assert (await client.get("/auth/me")).status_code == 401
    login = await make_client().post("/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert login.status_code == 401


async def test_a_signup_deletes_expired_accounts(make_client, db, monkeypatch):
    monkeypatch.setattr(settings, "account_ttl_hours", 24)
    old, recent = make_client(), make_client()
    old_user = await signup(old)
    await save_word(old, "casa")
    recent_user = await signup(recent)
    await _age_account(db, old_user["id"], 25)
    await _age_account(db, recent_user["id"], 23)

    await signup(make_client())

    remaining = set(await db.scalars(select(User.id)))
    assert old_user["id"] not in remaining
    assert recent_user["id"] in remaining
    assert await db.scalar(select(func.count()).select_from(User)) == 2


async def test_accounts_never_expire_by_default(make_client, db):
    client = make_client()
    user = await signup(client)
    await _age_account(db, user["id"], 24 * 365)
    assert (await client.get("/auth/me")).status_code == 200
