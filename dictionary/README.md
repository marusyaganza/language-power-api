# Dictionary

Looks up words in external dictionary APIs and turns their answers into `DictionaryEntry` objects. The rest of the app only sees `PROVIDERS` (one provider per language), `SearchResult` and `DictionaryEntry`.

## How it is organised

- `base.py`: `DictionaryProvider`, the contract every provider follows. `fetch` calls `_fetch_raw` (the API's answer, unchanged) and then `_parse` (that answer turned into a `SearchResult`).
- `entry.py`: `DictionaryEntry` and what each of its fields must hold, whatever the API.
- `merriam_webster/`: the code shared by the Merriam-Webster languages, `api.py` for the requests and parsing helpers and `provider.py` for the `MerriamWebsterProvider` base class.
- `en/`, `es/`: one package per language, each with its real provider and its mock. A language does not import from another language, so it can change API without affecting the others.
- `mock.py` and `fixtures/<language>/`: in mock mode, `_fetch_raw` reads a recorded answer instead of calling the API, and the real `_parse` runs on it.
- `providers.py`: `PROVIDERS`, the real or mock provider for each language, depending on `USE_MOCKS`.

## Adding a language

1. **`Language` value:** add it to `core/language.py`. The API then accepts it, and `/docs` lists it. The database stores languages as plain strings, so no migration is needed.
2. **Provider package:** create `dictionary/<language>/` with:
   - `<language>.py`: a provider that sets `language` and implements `_fetch_raw` and `_parse`. An API from an existing family subclasses that family's base (`MerriamWebsterProvider`); a new API subclasses `DictionaryProvider`, with its shared code in its own package next to `merriam_webster/`.
   - `mock.py`: `class Mock...(MockDictionaryMixin, <Provider>): pass`.
3. **Fixtures:** record a few real `_fetch_raw` answers as `dictionary/fixtures/<language>/<word>.json`, one file per word, named by the lowercased query. Pick neutral words of different levels and parts of speech.
4. **`PROVIDERS`:** add the language to both dictionaries in `providers.py`.
5. **API key:** add `<language>_api_key` to `settings.py` and to the names checked by `keys_required_without_mocks`, then:
   - a commented line in `.env.example` and a row in the README's environment variables table;
   - a fake value in the environment block at the top of `tests/conftest.py`, so tests never use a real key;
   - a Secret Manager secret, and its entry in `--set-secrets` in `.github/workflows/deploy.yml`.
6. **Games:** games with `all_languages` get the new language automatically. Language-specific games list their languages in `games/seed_data.py`. For example, the gender game needs the language in its `languages` list, and the provider must set `gender` to `masculine`, `feminine` or `both` (the database rejects other values). Run `python -m games.seed` afterwards.
7. **Tests:** parsing tests for the new provider in `tests/unit/`, run against its fixtures.
