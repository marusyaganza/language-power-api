# tests/unit/test_schemas.py
import pytest
from pydantic import ValidationError

from auth.schemas import LoginRequest, UserCreate
from games.schemas import GameSettingsUpdate
from settings import settings as app_settings
from words import schemas
from words.schemas import ExampleIn, WordCreate, WordUpdate


def word_create(**fields):
    return WordCreate(**{"name": "casa", "language": "es", "fl": "noun", "defs": ["house"], **fields})


def url(length):
    return "https://" + "x" * (length - len("https://"))


# --------------------------------------------------------------------------- #
# Words
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("translation", [None, "", "   "])
def test_example_translation_can_be_missing(translation):
    # Regression: PATCH /words/{id} rejected null translations with a 422.
    assert ExampleIn(text="mi casa", translation=translation).translation is None


# Each case: the limit, and the fields of a word that reaches a length or count n.
SIZE_LIMITS = {
    "name": (schemas.MAX_NAME_LENGTH, lambda n: {"name": "x" * n}),
    "uuid": (schemas.MAX_UUID_LENGTH, lambda n: {"uuid": "x" * n}),
    "fl": (schemas.MAX_FL_LENGTH, lambda n: {"fl": "x" * n}),
    "transcription": (schemas.MAX_TRANSCRIPTION_LENGTH, lambda n: {"transcription": "x" * n}),
    "img_desc": (schemas.MAX_IMG_DESC_LENGTH, lambda n: {"img_desc": "x" * n}),
    "audio_url": (schemas.MAX_URL_LENGTH, lambda n: {"audio_url": url(n)}),
    "img_url": (schemas.MAX_URL_LENGTH, lambda n: {"img_url": url(n)}),
    "stem length": (schemas.MAX_STEM_LENGTH, lambda n: {"stems": ["x" * n]}),
    "stem count": (schemas.MAX_STEMS, lambda n: {"stems": ["x"] * n}),
    "definition length": (schemas.MAX_DEFINITION_LENGTH, lambda n: {"defs": ["x" * n]}),
    "definition count": (schemas.MAX_DEFINITIONS, lambda n: {"defs": [f"d{i}" for i in range(n)]}),
    "example length": (schemas.MAX_EXAMPLE_LENGTH, lambda n: {"examples": [{"text": "x" * n}]}),
    "translation length": (
        schemas.MAX_EXAMPLE_LENGTH,
        lambda n: {"examples": [{"text": "x", "translation": "x" * n}]},
    ),
    "example count": (schemas.MAX_EXAMPLES, lambda n: {"examples": [{"text": "x"}] * n}),
}


@pytest.mark.parametrize(("limit", "fields"), SIZE_LIMITS.values(), ids=SIZE_LIMITS.keys())
def test_word_create_accepts_the_limit_and_rejects_one_more(limit, fields):
    word_create(**fields(limit))
    with pytest.raises(ValidationError):
        word_create(**fields(limit + 1))


@pytest.mark.parametrize(
    "case", ["definition length", "definition count", "example length", "example count", "audio_url", "img_url"]
)
def test_word_update_has_the_same_limits(case):
    limit, fields = SIZE_LIMITS[case]
    WordUpdate(**fields(limit))
    with pytest.raises(ValidationError):
        WordUpdate(**fields(limit + 1))


@pytest.mark.parametrize("value", ["javascript:alert(1)", "data:image/png;base64,AAAA", "ftp://x/a.mp3", "/a.mp3"])
@pytest.mark.parametrize("field", ["audio_url", "img_url"])
def test_media_urls_must_be_http(field, value):
    with pytest.raises(ValidationError):
        word_create(**{field: value})
    with pytest.raises(ValidationError):
        WordUpdate(**{field: value})


@pytest.mark.parametrize("value", ["https://a/x.mp3", "HTTP://a/x.mp3", "", None])
def test_media_urls_accept_http_or_nothing(value):
    assert word_create(audio_url=value, img_url=value).audio_url == (value or None)


@pytest.mark.parametrize("value", ["/sample-media/en/wheel.mp3", "/sample-media/es/ballena.svg"])
def test_mock_mode_accepts_the_sample_media_paths(value):
    assert app_settings.use_mocks
    assert word_create(audio_url=value).audio_url == value
    assert WordUpdate(img_url=value).img_url == value


@pytest.mark.parametrize(
    "value",
    [
        "/sample-media/../auth/me",
        "/sample-media/en/../../auth/me",
        "/sample-media/en/wheel.html",
        "/sample-media/en/wheel.mp3/../../../auth/me",
        "/sample-media/en/wheel.mp3?x=1",
        "/sample-media/fr/wheel.mp3",
        "/sample-media/en/Wheel.mp3",
        "//evil.example/sample-media/en/wheel.mp3",
        "/api/sample-media/en/wheel.mp3",  # ROOT_PATH is empty here
    ],
)
def test_only_exact_sample_media_paths_are_accepted(value):
    with pytest.raises(ValidationError):
        word_create(audio_url=value)


def test_sample_media_paths_follow_the_root_path(monkeypatch):
    monkeypatch.setattr(app_settings, "root_path", "/api")
    assert word_create(audio_url="/api/sample-media/en/wheel.mp3").audio_url == "/api/sample-media/en/wheel.mp3"
    with pytest.raises(ValidationError):
        word_create(audio_url="/sample-media/en/wheel.mp3")


def test_sample_media_paths_are_refused_outside_mock_mode(monkeypatch):
    monkeypatch.setattr(app_settings, "use_mocks", False)
    with pytest.raises(ValidationError):
        word_create(audio_url="/sample-media/en/wheel.mp3")


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
