from fastapi import APIRouter, HTTPException, Depends
from words.schemas import WordOut
from dictionary.providers import PROVIDERS
from auth.dependencies import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/words/search", response_model=list[WordOut])
async def search_word(query: str, language: str):
    provider = PROVIDERS.get(language)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    results = await provider.fetch(query)

    if not results:
        raise HTTPException(status_code=404, detail="Word not found")
    return results