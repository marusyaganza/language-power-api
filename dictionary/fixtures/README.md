# Mock dictionary fixtures

Dictionary entries for tests and local development (`USE_MOCKS=true`), in the JSON
format of the Merriam-Webster Dictionary API, so the real parsing code runs on them.
**They are made up for this project, not Merriam-Webster content:** the definitions,
examples, pronunciations and ids were written for it. Merriam-Webster's terms don't allow
storing or replaying its responses, so never add a recorded answer here.

| Language | Words | Why |
|---|---|---|
| `en/` | `wheel`, `brave`, `journey`, `although` | different parts of speech; `journey` has two entries (noun, verb); `wheel` has audio and a picture |
| `es/` | `ballena`, `idioma`, `ecologista`, `vivir` | the three noun genders (feminine, masculine, both) and a verb; `ballena` has audio and a picture |

Four words per language is what every game needs: the multiple-choice games use four.
One file per search query, named by the lowercased query.

Unusual shapes the parser handles (`bs`, `pseq`, cross-references, illustrations, audio
folders, malformed entries) are tested with small inline entries in
`tests/unit/test_mw.py`, not with fixtures.

`media/` holds the sample audio and pictures; see its README.
