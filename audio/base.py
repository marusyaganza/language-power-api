from abc import ABC, abstractmethod

from core.audio_engine import AudioEngine
from core.language import Language


class SpeechError(Exception):
    """The engine could not be reached or did not return audio.

    The message is safe to log and show: it never contains credentials.
    """


class SpeechTimeoutError(SpeechError):
    """The engine didn't answer in time."""


class UnknownVoiceError(ValueError):
    """The voice isn't one the engine offers for this language."""


class SpeechSynthesizer(ABC):
    """One text-to-speech engine: turns a word into MP3 audio.

    Each engine has its own synthesizer, like each language has its own
    dictionary provider. The rest of the app only calls `voices`,
    `default_voice` and `synthesize`.

    `synthesize` checks the voice, then calls `_synthesize_raw`, the only part
    that talks to the engine, so the mock (`audio.mock`) can replace just that.
    """

    engine: AudioEngine

    @abstractmethod
    def voices(self, language: Language) -> list[str]:
        """The voices offered for `language`, by short name (e.g. "Achernar")."""

    @abstractmethod
    def default_voice(self, language: Language) -> str:
        """The voice used when the user picks none; one of `voices(language)`."""

    async def synthesize(self, language: Language, text: str, voice: str) -> bytes:
        """Say `text` in `language` with `voice`, as MP3 bytes.

        Raises:
            UnknownVoiceError: `voice` isn't in `voices(language)`.
            SpeechTimeoutError: the engine didn't answer in time.
            SpeechError: the engine failed or is unreachable.
        """
        if voice not in self.voices(language):
            raise UnknownVoiceError(f"Unknown voice for {language}: {voice}")
        return await self._synthesize_raw(language, text, voice)

    @abstractmethod
    async def _synthesize_raw(self, language: Language, text: str, voice: str) -> bytes:
        """Ask the engine for the audio; `voice` is already checked.

        Raises:
            SpeechTimeoutError, SpeechError: as for `synthesize`.
        """
