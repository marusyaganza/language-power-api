from audio.base import SpeechSynthesizer
from audio.google import GoogleSpeechSynthesizer
from audio.mock import MockGoogleSpeechSynthesizer
from core.audio_engine import AudioEngine
from settings import settings


def build_synthesizers() -> dict[AudioEngine, SpeechSynthesizer]:
    """A synthesizer for every engine, mocked when `use_mocks` is on.

    Every engine gets one, cheap to make (nothing connects until the first
    generation): whether an engine is offered is `settings.audio_engines`,
    checked by the routes.
    """
    if settings.use_mocks:
        synthesizers = {AudioEngine.GOOGLE: MockGoogleSpeechSynthesizer}
    else:
        synthesizers = {AudioEngine.GOOGLE: GoogleSpeechSynthesizer}
    return {engine: synthesizer() for engine, synthesizer in synthesizers.items()}


SYNTHESIZERS = build_synthesizers()
