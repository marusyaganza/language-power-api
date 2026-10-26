from fastapi import Depends, FastAPI
from words.router import router as words_router
from auth.router import auth_router
from games.router import router as games_router, settings_router as game_settings_router
from fastapi.middleware.cors import CORSMiddleware

from core.proxy_signature import require_proxy_signature
from core.sentry import init_sentry
from settings import settings

# Before the app is created, so Sentry's FastAPI integration sees all of it.
init_sentry(settings)


if settings.docs_enabled:
    app = FastAPI()
else:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Every API route only answers requests from the frontend's proxy.
_from_proxy = [Depends(require_proxy_signature)]
app.include_router(words_router, dependencies=_from_proxy)
app.include_router(auth_router, dependencies=_from_proxy)
app.include_router(games_router, dependencies=_from_proxy)
app.include_router(game_settings_router, dependencies=_from_proxy)


@app.get("/health", include_in_schema=False)
async def health():
    """For uptime checks and the deploy smoke test: the process is serving.

    Not behind the proxy signature, and checks nothing else, so it reveals
    nothing and costs no database or Redis calls.
    """
    return {"status": "ok"}


if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
