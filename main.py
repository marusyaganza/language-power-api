from fastapi import FastAPI
from words.router import router as words_router
from auth.router import auth_router
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()
app.include_router(words_router)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)