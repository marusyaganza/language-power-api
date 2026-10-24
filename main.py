from fastapi import FastAPI
from words.router import router as words_router
from auth.router import auth_router
from games.router import router as games_router, settings_router as game_settings_router
from fastapi.middleware.cors import CORSMiddleware

from settings import settings


if settings.docs_enabled:
    app = FastAPI()
else:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(words_router)
app.include_router(auth_router)
app.include_router(games_router)
app.include_router(game_settings_router)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
