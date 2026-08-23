from fastapi import APIRouter, HTTPException
from words.schemas import WordOut
router = APIRouter()

from dictionary.en.mock import MockEnglishDictionaryProvider
from dictionary.es.mock import MockSpanishDictionaryProvider

PROVIDERS = {
    "en": MockEnglishDictionaryProvider,
    "es": MockSpanishDictionaryProvider,
}

@router.get("/word/search", response_model=list[WordOut])
async def search_word(query: str, language: str):
    print('query', query, language)
    provider_cls = PROVIDERS.get(language)
    if provider_cls is None:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")
    provider = provider_cls(language)

    results = await provider.fetch(query)

    if not results:
        raise HTTPException(status_code=404, detail="Word not found")
    return results