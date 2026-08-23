from fastapi import FastAPI
from words.router import router as words_router

app = FastAPI()
app.include_router(words_router)