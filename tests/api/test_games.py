# tests/api/test_games.py
import pytest
from sqlalchemy import select

from games.models import ReviewLog, WordProgress
from games.seed import sync_games
from tests.api.conftest import save_word, signup

pytestmark = pytest.mark.anyio


@pytest.fixture
async def games(db):
    """The games from games/seed_data.py, inside the test's transaction."""
    await sync_games(db)


async def game_id(client, game_type, language="es"):
    listed = (await client.get("/games", params={"language": language})).json()
    return next(g["id"] for g in listed if g["game_type"] == game_type)


async def start(client, game_type, **params):
    gid = await game_id(client, game_type)
    response = await client.get(f"/games/{gid}", params={"language": "es", **params})
    assert response.status_code == 200, response.text
    return gid, response.json()


async def answer(client, gid, session, word_id, text):
    return await client.post(f"/games/{gid}/answer", json={
        "session_id": session["session_id"], "word_id": word_id, "answer": text,
    })


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
        "type_word": 3, "select_def": 3, "select_word": 3,
        "audio": 1, "image": 1, "gender": 1,
    }
    # Never practiced, so every word is due.
    assert all(g["due_word_count"] == g["total_word_count"] for g in games_by_type.values())
    assert games_by_type["select_def"]["min_word_count"] == 4
    assert games_by_type["type_word"]["min_word_count"] == 1


async def test_unknown_game(client, games):
    assert (await client.get("/games/999999", params={"language": "es"})).status_code == 404


async def test_multiple_choice_game_needs_enough_words_for_the_options(client, games):
    for name in ["uno", "dos", "tres"]:
        await save_word(client, name)
    gid = await game_id(client, "select_def")
    response = await client.get(f"/games/{gid}", params={"language": "es"})
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
    gid, session = await start(client, "type_word")

    response = await answer(client, gid, session, word["id"], "Casa")
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
    gid, session = await start(client, "type_word")
    response = (await answer(client, gid, session, word["id"], "perro")).json()
    assert response["grade"] == "wrong"
    assert response["correct_answer"] == "casa"


async def test_a_question_can_be_answered_only_once(client, games):
    await save_word(client, "casa")
    await save_word(client, "perro")
    gid, session = await start(client, "type_word")
    first = session["questions"][0]["id"]

    assert (await answer(client, gid, session, first, "x")).json()["session_complete"] is False
    assert (await answer(client, gid, session, first, "casa")).status_code == 409


async def test_answer_for_a_word_not_in_the_session(client, games):
    await save_word(client, "casa")
    gid, session = await start(client, "type_word")
    assert (await answer(client, gid, session, 999999, "casa")).status_code == 404


async def test_answer_to_the_wrong_game(client, games):
    word = await save_word(client, "casa", gender="feminine")
    _gid, session = await start(client, "type_word")
    gender_game = await game_id(client, "gender")
    assert (await answer(client, gender_game, session, word["id"], "feminine")).status_code == 400


async def test_other_user_cannot_use_a_session(client, make_client, games):
    word = await save_word(client, "casa")
    gid, session = await start(client, "type_word")

    other = make_client()
    await signup(other)
    assert (await answer(other, gid, session, word["id"], "casa")).status_code == 404
    assert (await other.get(f"/games/result/{session['session_id']}")).status_code == 404


async def test_gender_game_gives_partial_credit(client, games):
    word = await save_word(client, "ecologista", gender="both")
    gid, session = await start(client, "gender")
    assert session["questions"][0]["options"] == ["masculine", "feminine"]

    response = (await answer(client, gid, session, word["id"], "masculine")).json()
    assert response["grade"] == "close"
    assert response["correct_answer"] == "both"


async def test_select_def_options_contain_the_answer(client, games):
    words = {}
    for name, meaning in [("perro", "dog"), ("gato", "cat"), ("casa", "house"), ("mesa", "table")]:
        words[name] = await save_word(client, name, defs=[meaning])
    gid, session = await start(client, "select_def")
    assert len(session["questions"]) == 4

    meaning_of = {w["id"]: w["defs"][0] for w in words.values()}
    for question in session["questions"]:
        assert len(question["options"]) == 4
        assert meaning_of[question["id"]] in question["options"]
        response = (await answer(client, gid, session, question["id"], meaning_of[question["id"]])).json()
        assert response["grade"] == "correct"


# --------------------------------------------------------------------------- #
# Spaced repetition across sessions
# --------------------------------------------------------------------------- #

async def test_a_learned_word_waits_until_it_is_due(client, games):
    word = await save_word(client, "casa")
    gid, session = await start(client, "type_word")
    await answer(client, gid, session, word["id"], "casa")

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
    gid, session = await start(client, "type_word")
    await answer(client, gid, session, word["id"], "casa")
    progress = await db.scalar(select(WordProgress).where(WordProgress.word_id == word["id"]))
    scheduled = progress.next_review_date

    _gid, review = await start(client, "type_word", mode="review")
    await answer(client, gid, review, word["id"], "casa")

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
    gid, session = await start(client, "type_word")
    questions = session["questions"]
    vocabulary = (await client.get("/words/vocabulary", params={"language": "es"})).json()
    name_of = {w["id"]: w["name"] for w in vocabulary["items"]}

    # One right, one wrong, one left unanswered.
    await answer(client, gid, session, questions[0]["id"], name_of[questions[0]["id"]])
    await answer(client, gid, session, questions[1]["id"], "nope")

    result = await client.get(f"/games/result/{session['session_id']}")
    assert result.status_code == 200, result.text
    body = result.json()
    assert (body["total_words"], body["correct"], body["wrong"], body["unanswered"]) == (3, 1, 1, 1)
    assert body["score_percent"] == 33

    # Finished: the last question takes no more answers.
    assert (await answer(client, gid, session, questions[2]["id"], "x")).status_code == 409
    # Reading the result again gives the same answer.
    assert (await client.get(f"/games/result/{session['session_id']}")).json() == body


async def test_result_of_an_unknown_session(client, games):
    assert (await client.get("/games/result/not-a-session")).status_code == 404
