"""Google Cloud Text-to-Speech, with Chirp 3 HD voices.

Credentials come from the environment (Application Default Credentials): on
Cloud Run, the service's own service account, which needs no role for this API,
only the API enabled in its project.
"""

from google.api_core import exceptions as google_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import texttospeech

from audio.base import SpeechError, SpeechSynthesizer, SpeechTimeoutError
from core.audio_engine import AudioEngine
from core.language import Language

# The accent of each language. Google has no Mexican Spanish locale for these
# voices (asking for es-MX returns es-US), and es-US is Latin American Spanish.
LOCALES = {Language.EN: "en-US", Language.ES: "es-US", Language.KO: "ko-KR"}

# Four female and four male Chirp 3 HD voices, all available in every locale
# above (checked 2026-11-09). Google's full name is "<locale>-Chirp3-HD-<voice>".
VOICES = ["Achernar", "Aoede", "Kore", "Leda", "Charon", "Fenrir", "Orus", "Puck"]
DEFAULT_VOICE = "Achernar"

TIMEOUT_SECONDS = 10


def voice_name(language: Language, voice: str) -> str:
    """Google's full name for a voice, e.g. "es-US-Chirp3-HD-Achernar"."""
    return f"{LOCALES[language]}-Chirp3-HD-{voice}"


class GoogleSpeechSynthesizer(SpeechSynthesizer):
    engine = AudioEngine.GOOGLE

    def __init__(self, client: texttospeech.TextToSpeechAsyncClient | None = None):
        # Created on first use, inside the running event loop, so importing
        # the app needs no credentials (tests and mocks never create one).
        self._client = client

    def voices(self, language: Language) -> list[str]:
        return list(VOICES)

    def default_voice(self, language: Language) -> str:
        return DEFAULT_VOICE

    async def _synthesize_raw(self, language: Language, text: str, voice: str) -> bytes:
        try:
            if self._client is None:
                self._client = texttospeech.TextToSpeechAsyncClient()
            response = await self._client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=LOCALES[language], name=voice_name(language, voice)
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
                timeout=TIMEOUT_SECONDS,
            )
        except google_exceptions.DeadlineExceeded as error:
            raise SpeechTimeoutError("Google Text-to-Speech didn't answer in time") from error
        except (google_exceptions.GoogleAPIError, auth_exceptions.GoogleAuthError) as error:
            raise SpeechError(f"Google Text-to-Speech failed: {type(error).__name__}") from error
        if not response.audio_content:
            raise SpeechError("Google Text-to-Speech returned no audio")
        return response.audio_content
