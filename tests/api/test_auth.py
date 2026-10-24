# tests/api/test_auth.py
import pytest
from sqlalchemy.exc import IntegrityError

from settings import settings
from users.models import User
from tests.api.conftest import PASSWORD, signup

pytestmark = pytest.mark.anyio


async def test_signup_logs_in_and_logout_ends_session(make_client):
    client = make_client()
    user = await signup(client)

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json() == user

    assert (await client.post("/auth/logout")).status_code == 200
    assert (await client.get("/auth/me")).status_code == 403


async def test_login_checks_the_password(make_client):
    client = make_client()
    user = await signup(client)
    await client.post("/auth/logout")

    wrong = await client.post("/auth/login", json={"email": user["email"], "password": "nope"})
    assert wrong.status_code == 401
    assert (await client.get("/auth/me")).status_code == 403

    right = await client.post("/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert right.status_code == 200
    assert (await client.get("/auth/me")).json()["id"] == user["id"]


async def test_unknown_email_gets_the_same_error_as_a_wrong_password(make_client):
    response = await make_client().post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_password_too_long_for_bcrypt_is_a_422_not_a_500(make_client):
    client = make_client()
    long_password = "a" * 73
    signup_response = await client.post(
        "/auth/signup", json={"email": "long@example.com", "password": long_password}
    )
    assert signup_response.status_code == 422
    login_response = await client.post(
        "/auth/login", json={"email": "long@example.com", "password": long_password}
    )
    assert login_response.status_code == 422


async def test_signup_rejects_a_taken_email(make_client):
    user = await signup(make_client())
    again = await make_client().post("/auth/signup", json={"email": user["email"], "password": PASSWORD})
    assert again.status_code == 400


async def test_email_case_does_not_matter(make_client):
    client = make_client()
    created = await client.post("/auth/signup", json={"email": "Mixed@Example.com", "password": PASSWORD})
    assert created.status_code == 201
    assert created.json()["email"] == "mixed@example.com"
    await client.post("/auth/logout")

    login = await client.post("/auth/login", json={"email": "MIXED@example.COM", "password": PASSWORD})
    assert login.status_code == 200
    again = await make_client().post("/auth/signup", json={"email": "mixed@EXAMPLE.com", "password": PASSWORD})
    assert again.status_code == 400


async def test_signup_password_shorter_than_8_characters_is_a_422(make_client):
    response = await make_client().post(
        "/auth/signup", json={"email": "short@example.com", "password": "a" * 7}
    )
    assert response.status_code == 422


async def test_database_rejects_an_uppercase_email(db):
    # The schemas lowercase emails; the constraint catches any other writer.
    with pytest.raises(IntegrityError):
        db.add(User(email="Upper@example.com", hashed_password="x"))
        await db.flush()


async def test_signup_can_be_closed(make_client, monkeypatch):
    monkeypatch.setattr(settings, "signup_enabled", False)
    response = await make_client().post(
        "/auth/signup", json={"email": "closed@example.com", "password": PASSWORD}
    )
    assert response.status_code == 403
    assert (await make_client().get("/auth/config")).json()["signup_enabled"] is False


async def test_requests_without_a_valid_session_are_rejected(make_client):
    client = make_client()
    assert (await client.get("/words/vocabulary", params={"language": "es"})).status_code == 403
    client.cookies.set(settings.session_cookie_name, "made-up-session-id")
    assert (await client.get("/auth/me")).status_code == 403
