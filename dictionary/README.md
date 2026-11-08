# Dictionary

Looks up words in each language's dictionary and turns the answers into `DictionaryEntry` objects. A dictionary is either an external API (Merriam-Webster for English and Spanish) or data imported into our database (Korean). The rest of the app only sees `PROVIDERS` (one provider per language), `SearchResult` and `DictionaryEntry`.

## How it is organised

- `base.py`: `DictionaryProvider`, the contract every provider follows. `fetch` calls `_fetch_raw` (the source's answer, unchanged) and then `_parse` (that answer turned into a `SearchResult`).
- `entry.py`: `DictionaryEntry` and what each of its fields must hold, whatever the source.
- `merriam_webster/`: the code shared by the Merriam-Webster languages, `api.py` for the requests and parsing helpers and `provider.py` for the `MerriamWebsterProvider` base class.
- `en/`, `es/`, `ko/`: one package per language, each with its real provider and its mock. A language does not import from another language, so it can change source without affecting the others. `ko/` also holds its tables and the script that imports them ([ko/README.md](ko/README.md)).
- `mock.py` and `fixtures/<language>/`: in mock mode, `_fetch_raw` reads a made-up answer instead of asking the source, and the real `_parse` runs on it. `SAMPLE_MEDIA` gives some of those words audio and a picture.
- `providers.py`: `PROVIDERS`, the real or mock provider for each language, depending on `USE_MOCKS`.

## Adding a language

1. **`Language` value:** add it to `core/language.py`. The API then accepts it, and `/docs` lists it. The database stores languages as plain strings, so no migration is needed for saved words. Add its English name to `_LANGUAGE_NAMES` in `words/service.py` (the demo's search-limit message).
2. **Provider package:** create `dictionary/<language>/` with:
   - `<language>.py`: a provider that sets `language` and implements `_fetch_raw` and `_parse`. An API from an existing family subclasses that family's base (`MerriamWebsterProvider`); a new API subclasses `DictionaryProvider`, with its shared code in its own package next to `merriam_webster/`.
   - `mock.py`: `class Mock...(MockDictionaryMixin, <Provider>): pass`.
3. **Fixtures:** write four made-up entries in the shape `_fetch_raw` returns as `dictionary/fixtures/<language>/<word>.json`, one file per word, named by the lowercased query, with different parts of speech (and genders, if the language has them). Never record real answers or copy imported rows: the dictionary's terms or license may not allow it, and this repository is MIT. See [fixtures/README.md](fixtures/README.md).
4. **`PROVIDERS`:** add the language to both dictionaries in `providers.py`, and its mock to the check at the top of `tests/conftest.py`.
5. **Where the data comes from**, one of:
   - **An API with a key:** add `<language>_api_key` to `settings.py` and to the names checked by `keys_required_without_mocks`, then:
     - a commented line in `.env.example` and a row in [docs/configuration.md](../docs/configuration.md);
     - a fake value in the environment block at the top of `tests/conftest.py`, so tests never use a real key;
     - a Secret Manager secret, and its entry in `--set-secrets` in `.github/workflows/deploy.yml`.
   - **Imported data** (like `ko/`): its tables in `dictionary/<language>/models.py`, imported in `alembic/env.py`, and a migration; an import script run by hand against each database (it isn't part of the image or of startup); queries in a `repository.py`, run in the provider's own session (`AsyncSessionLocal`), with database errors raised as `DictionaryError`. Credit the source wherever its text is shown, if its license asks for it.
6. **Games:** games with `all_languages` get the new language automatically. Language-specific games list their languages in `games/seed_data.py`. For example, the gender game needs the language in its `languages` list, and the provider must set `gender` to `masculine`, `feminine` or `both` (the database rejects other values). Run `python -m games.seed` afterwards. Check that typed answers are graded fairly in the language's script (`games/scoring.py`).
7. **Tests:** parsing tests for the new provider in `tests/unit/`, with small inline entries for the shapes its source can return; for imported data, also the import and the queries in `tests/api/`.
8. **Client:** the frontend lists its languages in `src/context/language.ts`.
