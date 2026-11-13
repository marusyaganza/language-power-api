"""Generating a word's audio by hand, before the word is saved with it.

A generation is held in Redis (`core.pending_media`) under a token; nothing
is written to the bucket until a word is saved with that token (words.service).
"""

import logging
import time
from dataclasses import dataclass

from audio import synthesizers
from audio.base import SpeechError, SpeechTimeoutError, UnknownVoiceError
from core import media_storage, pending_media
from core.audio_engine import AudioEngine
from core.language import Language
from settings import settings

logger = logging.getLogger(__name__)

PENDING_KIND = "audio"


class AudioError(Exception):
    """Base class for what the routes report to the client."""


class EngineNotAvailableError(AudioError):
    """The engine isn't one this deployment offers (`settings.audio_engines`)."""


class VoiceNotAvailableError(AudioError):
    """The voice isn't one the engine offers for this language."""


class EngineTimeoutError(AudioError):
    """The engine didn't answer in time; trying again may work."""


class EngineFailedError(AudioError):
    """The engine failed or couldn't be reached."""


@dataclass(frozen=True)
class Generation:
    token: str
    audio: bytes
    engine: AudioEngine
    voice: str


def _synthesizer(engine: AudioEngine):
    if engine not in settings.audio_engines:
        raise EngineNotAvailableError(f"Audio engine {engine.value!r} isn't available")
    return synthesizers.SYNTHESIZERS[engine]


def list_voices(language: Language) -> list[tuple[AudioEngine, list[str], str]]:
    """For each engine offered: its voices for `language`, and the default one."""
    result = []
    for engine in settings.audio_engines:
        synthesizer = synthesizers.SYNTHESIZERS[engine]
        result.append((engine, synthesizer.voices(language), synthesizer.default_voice(language)))
    return result


async def generate(user_id: int, language: Language, text: str, engine: AudioEngine, voice: str | None) -> Generation:
    """Say `text` with `engine` and hold the audio for the user until a word is saved with it.

    `voice` defaults to the engine's default voice for `language`. The held
    file records what the save needs: the engine and voice (the file's path),
    and the language and text (checked against the word it's saved to).

    Raises:
        EngineNotAvailableError: the deployment doesn't offer `engine`.
        VoiceNotAvailableError: `voice` isn't one of the engine's voices.
        EngineTimeoutError, EngineFailedError: the engine didn't deliver.
    """
    synthesizer = _synthesizer(engine)
    voice = voice or synthesizer.default_voice(language)
    started = time.perf_counter()
    try:
        audio = await synthesizer.synthesize(language, text, voice)
    except UnknownVoiceError as exc:
        raise VoiceNotAvailableError(f"Voice {voice!r} isn't available for this language") from exc
    except SpeechTimeoutError as exc:
        logger.warning("Audio generation timed out: engine=%s language=%s", engine, language)
        raise EngineTimeoutError("The audio engine didn't answer in time, try again") from exc
    except SpeechError as exc:
        logger.warning("Audio generation failed: engine=%s language=%s: %s", engine, language, exc)
        raise EngineFailedError("The audio engine failed, try again later") from exc
    # One line per generation, for comparing engines (audio plan B4).
    logger.info(
        "Audio generated: engine=%s voice=%s language=%s characters=%d ms=%d mode=manual",
        engine,
        voice,
        language,
        len(text),
        (time.perf_counter() - started) * 1000,
    )
    meta = {"engine": engine.value, "voice": voice, "language": language.value, "text": text}
    token = await pending_media.hold(PENDING_KIND, user_id, audio, meta)
    return Generation(token=token, audio=audio, engine=engine, voice=voice)


async def held_generation(user_id: int, token: str) -> pending_media.HeldFile | None:
    """The user's generation held under `token`, or None if it expired or never existed."""
    return await pending_media.get(PENDING_KIND, user_id, token)


async def store_generation(held: pending_media.HeldFile) -> str:
    """Upload a held generation for good and return its public URL.

    The path is `audio/<language>/<engine>/<sha256>.mp3`: the engine in the
    path says later where a word's audio came from.

    Raises:
        StorageError: there is no storage, or the upload failed.
    """
    storage = media_storage.STORAGE
    if storage is None:
        raise media_storage.StorageError("No media storage is configured")
    folder = f"audio/{held.meta['language']}/{held.meta['engine']}"
    return await storage.upload(held.data, media_storage.hashed_path(folder, held.data, "mp3"), "audio/mpeg")


async def discard_generation(user_id: int, token: str) -> None:
    """Stop holding a generation once the word is saved with it."""
    await pending_media.discard(PENDING_KIND, user_id, token)
