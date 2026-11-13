from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from core.audio_engine import AudioEngine
from core.enabled_language import EnabledLanguage

# Real dictionary names are at most 25 characters; 40 still fits phrases like
# "take something into account" and keeps each generation's cost predictable.
MAX_AUDIO_TEXT_LENGTH = 40
MAX_VOICE_LENGTH = 40


class AudioGenerateRequest(BaseModel):
    language: EnabledLanguage
    # The word's name. Sent as text, not a word id, so it works before a word is saved.
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_AUDIO_TEXT_LENGTH)]
    engine: AudioEngine = AudioEngine.GOOGLE
    # A short voice name from GET /audio/voices; the engine's default if left out.
    voice: str | None = Field(default=None, max_length=MAX_VOICE_LENGTH)


class GeneratedAudio(BaseModel):
    # Send it as `audio_token` when saving the word, within 24 hours.
    token: str
    # The audio as a `data:audio/mpeg;base64,...` URL, for <audio src> right away.
    preview: str
    engine: AudioEngine
    voice: str


class EngineVoices(BaseModel):
    engine: AudioEngine
    voices: list[str]
    default: str
