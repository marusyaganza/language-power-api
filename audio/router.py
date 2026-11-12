"""HTTP interface for generating a word's audio (personal deployment only).

Handlers only translate between HTTP and `audio.service`. Every route answers
404 where audio generation is off (`settings.audio_engines` empty), before
anything else is checked.
"""

import base64
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, status

from audio import service
from audio.schemas import AudioGenerateRequest, EngineVoices, GeneratedAudio
from auth.dependencies import get_current_user
from core.enabled_language import EnabledLanguage
from settings import settings


def require_audio_generation():
    if not settings.audio_engines:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(prefix="/audio", tags=["audio"], dependencies=[Depends(require_audio_generation)])

_STATUS_FOR_ERROR: dict[type[service.AudioError], int] = {
    service.EngineNotAvailableError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.VoiceNotAvailableError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.EngineTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    service.EngineFailedError: status.HTTP_502_BAD_GATEWAY,
}


@contextmanager
def _http_errors():
    """Turn an `AudioError` into an `HTTPException`; an unmapped one becomes a 500."""
    try:
        yield
    except service.AudioError as exc:
        raise HTTPException(
            status_code=_STATUS_FOR_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR), detail=str(exc)
        ) from exc


@router.get("/voices", response_model=list[EngineVoices])
async def get_voices(language: EnabledLanguage, current_user=Depends(get_current_user)):
    """The voices each engine offers for `language`, and its default, for the voice dropdown."""
    return [
        EngineVoices(engine=engine, voices=voices, default=default)
        for engine, voices, default in service.list_voices(language)
    ]


@router.post("/generate", response_model=GeneratedAudio)
async def generate_audio(payload: AudioGenerateRequest, current_user=Depends(get_current_user)):
    """Generate audio for a word's name, to listen to before saving it.

    Nothing is stored yet: the audio is held for 24 hours under `token`, and
    saving the word with that token keeps it. `preview` plays it right away.
    422 for an engine or voice that isn't offered, 504 if the engine timed
    out, 502 if it failed (both worth retrying).
    """
    with _http_errors():
        generation = await service.generate(
            current_user.id, payload.language, payload.text, payload.engine, payload.voice
        )
    preview = "data:audio/mpeg;base64," + base64.b64encode(generation.audio).decode("ascii")
    return GeneratedAudio(token=generation.token, preview=preview, engine=generation.engine, voice=generation.voice)
