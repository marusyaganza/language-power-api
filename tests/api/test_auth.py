# tests/api/test_auth.py
import pytest
from sqlalchemy.exc import IntegrityError

import auth.service
from settings import settings
from auth.rate_limit import AttemptLimiter
from auth.schemas import UserCreate
from users import service as users_service
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
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_checks_the_password(make_client):
    client = make_client()
    user = await signup(client)
    await client.post("/auth/logout")

    wrong = await client.post("/auth/login", json={"email": user["email"], "password": "nope"})
    assert wrong.status_code == 401
    assert (await client.get("/auth/me")).status_code == 401

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
    assert again.status_code == 409


async def test_email_case_does_not_matter(make_client):
    client = make_client()
    created = await client.post("/auth/signup", json={"email": "Mixed@Example.com", "password": PASSWORD})
    assert created.status_code == 201
    assert created.json()["email"] == "mixed@example.com"
    await client.post("/auth/logout")

    login = await client.post("/auth/login", json={"email": "MIXED@example.COM", "password": PASSWORD})
    assert login.status_code == 200
    again = await make_client().post("/auth/signup", json={"email": "mixed@EXAMPLE.com", "password": PASSWORD})
    assert again.status_code == 409


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
    assert (await client.get("/words/vocabulary", params={"language": "es"})).status_code == 401
    client.cookies.set(settings.session_cookie_name, "made-up-session-id")
    assert (await client.get("/auth/me")).status_code == 401


async def test_signup_race_for_one_email_is_a_409_not_a_500(make_client, monkeypatch):
    # Two simultaneous signups can both pass the "is this email taken?" check.
    # Simulate the second one by making that check miss.
    first = make_client()
    user = await signup(first)

    async def nobody_has_it(db, email):
        return None

    monkeypatch.setattr(users_service, "get_user_by_email", nobody_has_it)
    second = await make_client().post(
        "/auth/signup", json={"email": user["email"], "password": PASSWORD}
    )
    assert second.status_code == 409
    assert second.json() == {"detail": "Email already registered"}
    assert (await first.get("/auth/me")).json()["id"] == user["id"]


async def test_create_user_reports_a_taken_email(db):
    await users_service.create_user(db, UserCreate(email="dup@example.com", password=PASSWORD))
    with pytest.raises(users_service.EmailTakenError):
        await users_service.create_user(db, UserCreate(email="dup@example.com", password=PASSWORD))


async def test_create_user_keeps_other_database_errors(db):
    # Only a duplicate email is translated; anything else must still surface.
    # model_construct skips validation, so the uppercase email reaches the
    # database and breaks ck_users_email_lowercase instead.
    with pytest.raises(IntegrityError):
        await users_service.create_user(
            db, UserCreate.model_construct(email="Upper@example.com", password=PASSWORD)
        )


# --------------------------------------------------------------------------- #
# Rate limits
# --------------------------------------------------------------------------- #

async def login(client, email, password):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def test_too_many_logins_for_one_email_are_a_429_even_with_the_right_password(make_client):
    client = make_client()
    user = await signup(client)
    await client.post("/auth/logout")

    for _ in range(settings.login_attempt_limit):
        assert (await login(client, user["email"], "wrong-password")).status_code == 401

    response = await login(client, user["email"], PASSWORD)
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts, try again later"}
    retry_after = int(response.headers["retry-after"])
    assert 0 < retry_after <= settings.login_attempt_window_seconds
    assert (await client.get("/auth/me")).status_code == 401  # not logged in

    # Other emails are counted separately, and the count ignores case.
    assert (await login(client, "someone-else@example.com", PASSWORD)).status_code == 401
    assert (await login(client, user["email"].upper(), PASSWORD)).status_code == 429


async def test_a_successful_login_starts_the_count_over(make_client):
    client = make_client()
    user = await signup(client)

    for _ in range(settings.login_attempt_limit - 1):
        await login(client, user["email"], "wrong-password")
    assert (await login(client, user["email"], PASSWORD)).status_code == 200

    for _ in range(settings.login_attempt_limit - 1):
        assert (await login(client, user["email"], "wrong-password")).status_code == 401
    assert (await login(client, user["email"], PASSWORD)).status_code == 200


async def test_a_refused_login_does_not_reach_the_database(make_client, monkeypatch):
    client = make_client()
    for _ in range(settings.login_attempt_limit):
        await login(client, "target@example.com", "guess")

    async def must_not_run(db, email):
        raise AssertionError("looked up the user for a refused attempt")

    monkeypatch.setattr(users_service, "get_user_by_email", must_not_run)
    assert (await login(client, "target@example.com", "guess")).status_code == 429


async def test_signups_are_limited_across_everyone(make_client, monkeypatch):
    monkeypatch.setattr(auth.service, "_signup_limiter", AttemptLimiter(2, 3600))
    await signup(make_client())
    await signup(make_client())

    response = await make_client().post(
        "/auth/signup", json={"email": "third@example.com", "password": PASSWORD}
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_closed_signups_do_not_use_up_the_signup_limit(make_client, monkeypatch):
    monkeypatch.setattr(auth.service, "_signup_limiter", AttemptLimiter(1, 3600))
    monkeypatch.setattr(settings, "signup_enabled", False)
    closed = await make_client().post(
        "/auth/signup", json={"email": "closed@example.com", "password": PASSWORD}
    )
    assert closed.status_code == 403

    monkeypatch.setattr(settings, "signup_enabled", True)
    await signup(make_client())
