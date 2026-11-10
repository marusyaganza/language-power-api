"""A synthesizer that returns a short tone instead of calling the engine.

Used when the `use_mocks` setting is on (see `audio.synthesizers`): in tests
and local development. Only the call to the engine is replaced, so voices and
their checks are the real ones.

`mock.mp3` is a 0.4 s, 660 Hz tone made for this project with ffmpeg:

    ffmpeg -f lavfi -i "sine=frequency=660:duration=0.4" \
      -af "afade=t=in:d=0.05,afade=t=out:st=0.3:d=0.1" -ac 1 -ar 22050 -b:a 32k \
      -map_metadata -1 -id3v2_version 0 -write_xing 0 mock.mp3
"""

import hashlib
from pathlib import Path

from audio.google import GoogleSpeechSynthesizer
from core.language import Language

MOCK_MP3 = (Path(__file__).parent / "mock.mp3").read_bytes()


def mock_audio(language: Language, text: str, voice: str) -> bytes:
    """The tone, with an ID3v1 tag that differs per language, text and voice.

    Like a real engine, different words give different files (and so different
    names in the bucket), and the same word gives the same file. ID3v1 is a
    fixed 128-byte block at the end that players ignore; its title holds a
    hash, since the text itself may not fit its Latin-1 encoding.
    """
    title = hashlib.sha256(f"{language}|{voice}|{text}".encode()).hexdigest()[:30]
    tag = b"TAG" + title.encode("ascii") + bytes(128 - 3 - 30)
    return MOCK_MP3 + tag


class MockGoogleSpeechSynthesizer(GoogleSpeechSynthesizer):
    async def _synthesize_raw(self, language: Language, text: str, voice: str) -> bytes:
        return mock_audio(language, text, voice)
