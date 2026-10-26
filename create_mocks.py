"""
Temporary script: calls the real dictionary APIs and saves each response
as a JSON fixture file, for use as mocks in test_mode later.

Run once with your real .env in place, then this file's job is done -
delete it whenever you're happy with the fixtures.
"""

import asyncio
import json

import httpx

from dictionary.en.en import API_URL as ENGLISH_API_URL
from dictionary.es.es import API_URL as SPANISH_API_URL
from dictionary.mock import FIXTURES_DIR  # where the mock providers read them
from settings import settings

WORDS = {
    "en": [
        "egalitarian",
        "rubber",
        "pussy",
        "heart",
        "wheel",
        "voluminous",
        "fowl",
        "murther",
    ],
    "es": [
        "idioma",
        "hola",
        "caerse",
        "asi",
        "tener",
        "ser",
        "llover",
        "ecologista",
        "bully",
        "instruction",
        "empezar",
        "ballena",
    ],
}

API_CONFIG = {
    "en": {"url": ENGLISH_API_URL, "key": settings.english_api_key.get_secret_value()},
    "es": {"url": SPANISH_API_URL, "key": settings.spanish_api_key.get_secret_value()},
}

# keep this modest so you don't trip a rate limit on a free-tier API key
CONCURRENCY_LIMIT = 5


async def fetch_word(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, language: str, word: str
) -> None:
    config = API_CONFIG[language]
    url = f"{config['url']}/{word}?key={config['key']}"  # <-- adjust if your API expects a query param instead

    # NOTE: swap this for headers={"Authorization": f"Bearer {config['key']}"}
    # if your API expects the key in a header rather than the query string
    params = {"key": config["key"]}

    async with semaphore:
        try:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"FAILED  {language}/{word}: {exc}")
            return

    out_dir = FIXTURES_DIR / language
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{word}.json"

    # ensure_ascii=False so Spanish accented characters stay readable, not \uXXXX escaped
    out_path.write_text(
        json.dumps(response.json(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"saved   {language}/{word} -> {out_path}")


async def main() -> None:
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_word(client, semaphore, language, word)
            for language, words in WORDS.items()
            for word in words
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())