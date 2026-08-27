from fastapi import FastAPI
from words.router import router as words_router

from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()
app.include_router(words_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)