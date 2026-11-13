# tests/unit/test_speech.py
"""Speech synthesizers: voices, the mock's audio, and how Google is called (with a fake client)."""

from types import SimpleNamespace

import pytest
from google.api_core import exceptions as google_exceptions
from google.cloud import texttospeech

from audio.base import SpeechError, SpeechTimeoutError, UnknownVoiceError
from audio.google import LOCALES, TIMEOUT_SECONDS, GoogleSpeechSynthesizer
from audio.mock import MOCK_MP3, MockGoogleSpeechSynthesizer
from core.language import Language

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeClient:
    """Stands in for TextToSpeechAsyncClient: records the call, answers or raises."""

    def __init__(self, audio=b"mp3 bytes", error=None):
        self.audio, self.error, self.calls = audio, error, []

    async def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(audio_content=self.audio)


# --------------------------------------------------------------------------- #
# Voices
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("language", list(Language))
def test_every_language_has_an_accent_and_a_default_voice_it_offers(language):
    synthesizer = GoogleSpeechSynthesizer()

    assert language in LOCALES
    assert synthesizer.default_voice(language) in synthesizer.voices(language)


async def test_an_unknown_voice_is_rejected_before_calling_the_engine():
    client = FakeClient()

    with pytest.raises(UnknownVoiceError):
        await GoogleSpeechSynthesizer(client).synthesize(Language.EN, "wheel", "Nobody")
    assert client.calls == []


# --------------------------------------------------------------------------- #
# Google, with a fake client
# --------------------------------------------------------------------------- #


async def test_google_is_asked_for_mp3_in_the_languages_accent():
    client = FakeClient()

    audio = await GoogleSpeechSynthesizer(client).synthesize(Language.ES, "ballena", "Achernar")

    assert audio == b"mp3 bytes"
    [call] = client.calls
    assert call["input"].text == "ballena"
    assert (call["voice"].language_code, call["voice"].name) == ("es-US", "es-US-Chirp3-HD-Achernar")
    assert call["audio_config"].audio_encoding == texttospeech.AudioEncoding.MP3
    assert call["timeout"] == TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        (google_exceptions.DeadlineExceeded("slow"), SpeechTimeoutError),
        (google_exceptions.ServiceUnavailable("down"), SpeechError),
        (google_exceptions.PermissionDenied("API not enabled"), SpeechError),
    ],
)
async def test_google_errors_become_speech_errors(error, raised):
    with pytest.raises(raised):
        await GoogleSpeechSynthesizer(FakeClient(error=error)).synthesize(Language.EN, "wheel", "Achernar")


async def test_no_audio_from_google_is_an_error():
    with pytest.raises(SpeechError, match="no audio"):
        await GoogleSpeechSynthesizer(FakeClient(audio=b"")).synthesize(Language.EN, "wheel", "Achernar")


def test_making_a_google_synthesizer_needs_no_credentials():
    # Created at import (audio.synthesizers); the client only comes with the first call.
    assert GoogleSpeechSynthesizer()._client is None


# --------------------------------------------------------------------------- #
# The mock
# --------------------------------------------------------------------------- #


async def test_the_mock_returns_the_tone_with_a_128_byte_tag():
    audio = await MockGoogleSpeechSynthesizer().synthesize(Language.KO, "바퀴", "Achernar")

    assert audio.startswith(MOCK_MP3)
    assert audio[len(MOCK_MP3) :].startswith(b"TAG")
    assert len(audio) == len(MOCK_MP3) + 128


async def test_the_mock_gives_the_same_word_the_same_file_and_others_a_different_one():
    mock = MockGoogleSpeechSynthesizer()

    wheel = await mock.synthesize(Language.EN, "wheel", "Achernar")

    assert wheel == await mock.synthesize(Language.EN, "wheel", "Achernar")
    assert wheel != await mock.synthesize(Language.EN, "whale", "Achernar")
    assert wheel != await mock.synthesize(Language.EN, "wheel", "Puck")
    assert wheel != await mock.synthesize(Language.ES, "wheel", "Achernar")


async def test_the_mock_checks_voices_like_the_real_one():
    with pytest.raises(UnknownVoiceError):
        await MockGoogleSpeechSynthesizer().synthesize(Language.EN, "wheel", "Nobody")
