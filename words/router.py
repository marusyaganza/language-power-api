from fastapi import APIRouter, HTTPException
from words.schemas import WordOut
router = APIRouter()

from dictionary.providers import PROVIDERS

@router.get("/words/search", response_model=list[WordOut])
async def search_word(query: str, language: str):
    provider = PROVIDERS.get(language)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    results = await provider.fetch(query)

    if not results:
        raise HTTPException(status_code=404, detail="Word not found")
    return results