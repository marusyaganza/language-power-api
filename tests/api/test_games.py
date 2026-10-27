# tests/api/test_games.py
import pytest
from sqlalchemy import select, update

from games.models import Game, ReviewLog, WordProgress
from games.seed import sync_games
from games.session_store import GAME_SESSION_TTL_SECONDS, _game_session_key
from tests.api.conftest import save_word, signup

pytestmark = pytest.mark.anyio


@pytest.fixture
async def games(db):
    """The games from games/seed_data.py, inside the test's transaction."""
    await sync_games(db)


async def game_id(client, game_type, language="es"):
    listed = (await client.get("/games", params={"language": language})).json()
    return next(g["id"] for g in listed if g["game_type"] == game_type)


async def start(client, game_type, **body):
    gid = await game_id(client, game_type)
    response = await client.post(f"/games/{gid}/sessions", json={"language": "es", **body})
    assert response.status_code == 201, response.text
    return gid, response.json()


async def answer(client, session, word_id, text):
    return await client.post(
        f"/games/sessions/{session['session_id']}/answers",
        json={
            "word_id": word_id,
            "answer": text,
        },
    )


async def result(client, session):
    return await client.post(f"/games/sessions/{session['session_id']}/result")


# --------------------------------------------------------------------------- #
# Listing and starting
# --------------------------------------------------------------------------- #


async def test_list_counts_the_words_each_game_can_use(client, games):
    await save_word(client, "plain")
    await save_word(client, "sound", audio_url="https://a/x.mp3")
    await save_word(client, "picture", img_url="https://i/x.png", gender="feminine")

    games_by_type = {g["game_type"]: g for g in (await client.get("/games", params={"language": "es"})).json()}
    counts = {t: g["total_word_count"] for t, g in games_by_type.items()}
    assert counts == {
        "type_word": 3,
        "select_def": 3,
        "select_word": 3,
        "audio": 1,
        "image": 1,
        "gender": 1,
    }
    # Never practiced, so every word is due.
    assert all(g["due_word_count"] == g["total_word_count"] for g in games_by_type.values())
    assert games_by_type["select_def"]["min_word_count"] == 4
    assert games_by_type["type_word"]["min_word_count"] == 1


async def test_unknown_game(client, games):
    assert (await client.post("/games/999999/sessions", json={"language": "es"})).status_code == 404


async def test_start_needs_a_language(client, games):
    gid = await game_id(client, "type_word")
    assert (await client.post(f"/games/{gid}/sessions", json={})).status_code == 422


async def test_an_unsupported_language_is_rejected(client, games):
    gid = await game_id(client, "type_word")
    listed = await client.get("/games", params={"language": "xx"})
    started = await client.post(f"/games/{gid}/sessions", json={"language": "xx"})
    assert [listed.status_code, started.status_code] == [422, 422]


async def test_old_game_session_routes_are_gone(client, games):
    gid, session = await start(client, "type_word")
    assert (await client.get(f"/games/{gid}", params={"language": "es"})).status_code in (404, 405)
    assert (await client.get(f"/games/result/{session['session_id']}")).status_code in (404, 405)


async def test_multiple_choice_game_needs_enough_words_for_the_options(client, games):
    for name in ["uno", "dos", "tres"]:
        await save_word(client, name)
    gid = await game_id(client, "select_def")
    response = await client.post(f"/games/{gid}/sessions", json={"language": "es"})
    assert response.status_code == 409


async def test_type_word_question_hides_the_word_in_its_clues(client, games):
    word = await save_word(client, "casa", defs=["una casa grande", "a building"])
    _gid, session = await start(client, "type_word")
    assert session["questions"][0]["id"] == word["id"]
    assert session["questions"][0]["question"] == ["una ___ grande", "a building"]
    assert "casa" not in str(session["questions"])  # the answer never reaches the client


# --------------------------------------------------------------------------- #
# Playing
# --------------------------------------------------------------------------- #


async def test_answer_is_graded_and_progress_saved(client, db, games):
    word = await save_word(client, "casa")
    _gid, session = await start(client, "type_word")

    response = await answer(client, session, word["id"], "Casa")
    assert response.status_code == 200, response.text
    assert response.json() == {"grade": "correct", "correct_answer": None, "session_complete": True}

    # Progress is saved before the response is returned.
    progress = await db.scalar(select(WordProgress).where(WordProgress.word_id == word["id"]))
    assert progress is not None
    assert progress.game_type == "type_word"
    assert progress.last_reviewed_at is not None
    logs = (await db.scalars(select(ReviewLog).where(ReviewLog.word_progress_id == progress.id))).all()
    assert [log.grade for log in logs] == ["correct"]


async def test_wrong_answer_reveals_the_expected_one(client, games):
    word = await save_word(client, "casa")
    _gid, session = await start(client, "type_word")
    response = (await answer(client, session, word["id"], "perro")).json()
    assert response["grade"] == "wrong"
    assert response["correct_answer"] == "casa"


async def test_a_question_can_be_answered_only_once(client, games):
    await save_word(client, "casa")
    await save_word(client, "perro")
    _gid, session = await start(client, "type_word")
    first = session["questions"][0]["id"]

    assert (await answer(client, session, first, "x")).json()["session_complete"] is False
    assert (await answer(client, session, first, "casa")).status_code == 409


async def test_answer_for_a_word_not_in_the_session(client, games):
    await save_word(client, "casa")
    _gid, session = await start(client, "type_word")
    assert (await answer(client, session, 999999, "casa")).status_code == 404


async def test_answering_restarts_the_session_lifetime(client, redis, games):
    await save_word(client, "casa")
    await save_word(client, "perro")
    _gid, session = await start(client, "type_word")
    key = _game_session_key(session["session_id"])
    await redis.expire(key, 60)  # as if the session had been idle for 19 minutes

    await answer(client, session, session["questions"][0]["id"], "x")
    assert await redis.ttl(key) > GAME_SESSION_TTL_SECONDS - 10


async def test_an_expired_session_is_not_found(client, redis, games):
    word = await save_word(client, "casa")
    _gid, session = await start(client, "type_word")
    await redis.delete(_game_session_key(session["session_id"]))  # what expiry does
    assert (await answer(client, session, word["id"], "casa")).status_code == 404
    assert (await result(client, session)).status_code == 404


async def test_other_user_cannot_use_a_session(client, make_client, games):
    word = await save_word(client, "casa")
    _gid, session = await start(client, "type_word")

    other = make_client()
    await signup(other)
    assert (await answer(other, session, word["id"], "casa")).status_code == 404
    assert (await result(other, session)).status_code == 404


async def test_gender_game_gives_partial_credit(client, games):
    word = await save_word(client, "ecologista", gender="both")
    _gid, session = await start(client, "gender")
    assert session["questions"][0]["options"] == ["masculine", "feminine"]

    response = (await answer(client, session, word["id"], "masculine")).json()
    assert response["grade"] == "close"
    assert response["correct_answer"] == "both"


async def test_select_def_options_contain_the_answer(client, games):
    words = {}
    for name, meaning in [("perro", "dog"), ("gato", "cat"), ("casa", "house"), ("mesa", "table")]:
        words[name] = await save_word(client, name, defs=[meaning])
    _gid, session = await start(client, "select_def")
    assert len(session["questions"]) == 4

    meaning_of = {w["id"]: w["defs"][0] for w in words.values()}
    for question in session["questions"]:
        assert len(question["options"]) == 4
        assert meaning_of[question["id"]] in question["options"]
        response = (await answer(client, session, question["id"], meaning_of[question["id"]])).json()
        assert response["grade"] == "correct"


async def test_select_def_options_consider_the_whole_pool(client, db, games):
    # "ente" means "being", which is also a meaning of "ser" the noun. In the
    # question for "ser" the verb, the player only sees "ser", so "being" would
    # be a second correct option. Excluding it needs both "ser" entries from
    # the pool, which is loaded as summaries (words.service.get_word_summaries).
    ser_verb = await save_word(client, "ser", uuid="ser-verb", defs=["to be"], examples=[{"text": "quiero ser feliz"}])
    await save_word(client, "ser", uuid="ser-noun", defs=["being"])
    await save_word(client, "ente", defs=["being"])
    for name, meaning in [("perro", "dog"), ("gato", "cat"), ("casa", "house")]:
        await save_word(client, name, defs=[meaning])
    # More questions than words, so "ser" the verb is always asked (5 of 6
    # words would leave it out one time in six).
    await db.execute(
        update(Game).where(Game.game_type == "select_def").values(default_config={"words_per_session": 10})
    )

    _gid, session = await start(client, "select_def")
    [question] = [q for q in session["questions"] if q["id"] == ser_verb["id"]]
    assert sorted(question["options"]) == ["cat", "dog", "house", "to be"]
    # The session's own words are still loaded in full.
    assert question["additional_info"]["examples"][0]["text"] == "quiero ser feliz"


# --------------------------------------------------------------------------- #
# Spaced repetition across sessions
# --------------------------------------------------------------------------- #


async def test_a_learned_word_waits_until_it_is_due(client, games):
    word = await save_word(client, "casa")
    gid, session = await start(client, "type_word")
    await answer(client, session, word["id"], "casa")

    # A correct first answer schedules the next review a day later.
    listed = next(g for g in (await client.get("/games", params={"language": "es"})).json() if g["id"] == gid)
    assert (listed["total_word_count"], listed["due_word_count"]) == (1, 0)
    assert listed["next_due_at"] is not None

    _gid, spaced = await start(client, "type_word")
    assert spaced["questions"] == []
    _gid, review = await start(client, "type_word", mode="review")
    assert [q["id"] for q in review["questions"]] == [word["id"]]


async def test_extra_practice_does_not_move_the_schedule(client, db, games):
    word = await save_word(client, "casa")
    _gid, session = await start(client, "type_word")
    await answer(client, session, word["id"], "casa")
    progress = await db.scalar(select(WordProgress).where(WordProgress.word_id == word["id"]))
    scheduled = progress.next_review_date

    _gid, review = await start(client, "type_word", mode="review")
    await answer(client, review, word["id"], "casa")

    await db.refresh(progress)
    assert progress.next_review_date == scheduled
    logs = (await db.scalars(select(ReviewLog).where(ReviewLog.word_progress_id == progress.id))).all()
    assert len(logs) == 2


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


async def test_result_finishes_the_session_and_counts_unanswered(client, games):
    for name in ["uno", "dos", "tres"]:
        await save_word(client, name)
    _gid, session = await start(client, "type_word")
    questions = session["questions"]
    vocabulary = (await client.get("/words/vocabulary", params={"language": "es"})).json()
    name_of = {w["id"]: w["name"] for w in vocabulary["items"]}

    # One right, one wrong, one left unanswered.
    await answer(client, session, questions[0]["id"], name_of[questions[0]["id"]])
    await answer(client, session, questions[1]["id"], "nope")

    response = await result(client, session)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_words"], body["correct"], body["wrong"], body["unanswered"]) == (3, 1, 1, 1)
    assert body["score_percent"] == 33

    # Finished: the last question takes no more answers.
    assert (await answer(client, session, questions[2]["id"], "x")).status_code == 409
    # Asking for the result again is not an error and gives the same result.
    again = await result(client, session)
    assert again.status_code == 200
    assert again.json() == body


async def test_result_of_an_unknown_session(client, games):
    assert (await result(client, {"session_id": "not-a-session"})).status_code == 404
