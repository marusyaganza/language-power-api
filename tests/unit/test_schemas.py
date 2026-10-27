# tests/unit/test_schemas.py
import pytest
from pydantic import ValidationError

from auth.schemas import LoginRequest, UserCreate
from games.schemas import GameSettingsUpdate
from words.schemas import ExampleUpdate, WordCreate, WordUpdate


def word_create(**fields):
    return WordCreate(**{"name": "casa", "language": "es", "fl": "noun", "defs": ["house"], **fields})


# --------------------------------------------------------------------------- #
# Words
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("translation", [None, "", "   "])
def test_example_translation_can_be_missing(translation):
    # Regression: PATCH /words/{id} rejected null translations with a 422.
    assert ExampleUpdate(text="mi casa", translation=translation).translation is None


def test_definitions_are_stripped_and_repeats_dropped():
    assert word_create(defs=[" house ", "home", "House", "home "]).defs == ["house", "home"]


@pytest.mark.parametrize("defs", [[], [""], ["house", "  "]])
def test_word_create_rejects_missing_or_blank_definitions(defs):
    with pytest.raises(ValidationError):
        word_create(defs=defs)


def test_word_update_drops_blank_definitions_but_needs_one():
    assert WordUpdate(defs=["house", " ", "house"]).defs == ["house"]
    with pytest.raises(ValidationError):
        WordUpdate(defs=[" "])


@pytest.mark.parametrize(
    ("gender", "stored"),
    [("masculine", "masculine"), ("feminine", "feminine"), ("both", "both"), ("", None), (None, None)],
)
def test_gender_values(gender, stored):
    assert word_create(gender=gender).gender == stored


def test_unknown_gender_is_rejected():
    with pytest.raises(ValidationError):
        word_create(gender="neuter")


# --------------------------------------------------------------------------- #
# Game settings
# --------------------------------------------------------------------------- #


def settings(**fields):
    return GameSettingsUpdate(
        **{"learning_steps_minutes": [15, 1440], "graduating_interval_days": 6, "strict_mode": False, **fields}
    )


def test_valid_settings():
    assert settings().learning_steps_minutes == [15, 1440]


@pytest.mark.parametrize(
    "fields",
    [
        {"learning_steps_minutes": []},  # at least one step
        {"learning_steps_minutes": [1, 2, 3, 4, 5, 6]},  # at most five
        {"learning_steps_minutes": [15, 15]},  # must get longer
        {"learning_steps_minutes": [60, 15]},
        {"learning_steps_minutes": [0, 15]},  # at least a minute
        {"learning_steps_minutes": [15, 91 * 24 * 60]},  # at most 90 days
        {"graduating_interval_days": 0},
        {"graduating_interval_days": 91},
        # Graduating (1 day) would come sooner than the last step (2 days).
        {"learning_steps_minutes": [15, 2880], "graduating_interval_days": 1},
    ],
)
def test_invalid_settings_are_rejected(fields):
    with pytest.raises(ValidationError):
        settings(**fields)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("schema", [UserCreate, LoginRequest])
def test_password_up_to_72_bytes_is_accepted(schema):
    assert schema(email="a@example.com", password="a" * 72).password == "a" * 72


# Regression: bcrypt 5 raises on passwords over 72 bytes, which was a 500.
# "é" is two bytes, so 37 of them are 74 bytes but only 37 characters.
@pytest.mark.parametrize("schema", [UserCreate, LoginRequest])
@pytest.mark.parametrize("password", ["a" * 73, "é" * 37])
def test_password_over_72_bytes_is_rejected(schema, password):
    with pytest.raises(ValidationError):
        schema(email="a@example.com", password=password)


@pytest.mark.parametrize("password", ["a" * 8, "é" * 8])  # characters, not bytes
def test_new_password_of_8_characters_is_accepted(password):
    assert UserCreate(email="a@example.com", password=password).password == password


def test_new_password_under_8_characters_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="a" * 7)


def test_login_has_no_minimum_password_length():
    # A short password just fails to match; login does not reveal the rule.
    assert LoginRequest(email="a@example.com", password="nope").password == "nope"


@pytest.mark.parametrize("schema", [UserCreate, LoginRequest])
def test_email_is_trimmed_and_lowercased(schema):
    user = schema(email="  Foo.Bar@Example.COM ", password="a" * 8)
    assert user.email == "foo.bar@example.com"
