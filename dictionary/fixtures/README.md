# Mock dictionary fixtures

Dictionary entries for tests and local development (`USE_MOCKS=true`), in the JSON
format of the Merriam-Webster Dictionary API, so the real parsing code runs on them.
**They are made up for this project, not Merriam-Webster content:** the definitions,
examples, pronunciations and ids were written for it. Merriam-Webster's terms don't allow
storing or replaying its responses, so never add a recorded answer here.

| Language | Words | Why |
|---|---|---|
| `en/` | `cat`, `wheel`, `brave`, `journey`, `although` | different parts of speech; `journey` has two entries (noun, verb); `cat` has audio and a picture |
| `es/` | `gato`, `ballena`, `idioma`, `ecologista`, `vivir` | the three noun genders (feminine, masculine, both) and a verb; `gato` has audio and a picture |

Four words per language is what every game needs: the multiple-choice games use four.
One file per search query, named by the lowercased query.

Unusual shapes the parser handles (`bs`, `pseq`, cross-references, illustrations, audio
folders, malformed entries) are tested with small inline entries in
`tests/unit/test_mw.py`, not with fixtures.

## Sample audio and pictures

`SAMPLE_MEDIA` in `dictionary/mock.py` gives `cat` and `gato` an `audio_url` and an
`img_url` on other sites, which the browser loads directly. They are free to use:

| Word | What | Source and license |
|---|---|---|
| `cat` | audio, US English, 0.5 s | [En-us-cat.ogg](https://commons.wikimedia.org/wiki/File:En-us-cat.ogg) by Dvortygirl, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), served by Wikimedia Commons as MP3 |
| `gato` | audio, Spain Spanish | [LL-Q1321 (spa)-Millars-gato.wav](https://commons.wikimedia.org/wiki/File:LL-Q1321_(spa)-Millars-gato.wav) by Millars (Lingua Libre), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), served by Wikimedia Commons as MP3 |
| both | picture of a cat | [Lorem Picsum](https://picsum.photos/) photo 40, by Ryan McGuire on [Unsplash](https://unsplash.com/photos/N-1XGL54pQg), [Unsplash License](https://unsplash.com/license) |

Pick new ones the same way: an explicit free license, a small MP3 for audio (Safari can't
play Ogg), and never Merriam-Webster media.
