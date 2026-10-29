# Sample media

Audio and pictures for the mock dictionaries, served at `/sample-media/<language>/` in
mock mode only. A file named `<word>.mp3` or `<word>.svg` becomes the `audio_url` or
`img_url` of the entries for that word (`dictionary/mock.py`). A test checks that every
file here belongs to a fixture word.

| File | What |
|---|---|
| `en/wheel.mp3` | "wheel", US English voice, 0.64 s |
| `es/ballena.mp3` | "ballena", Spain Spanish voice, 0.63 s |
| `en/wheel.svg` | a spoked wheel, drawn by hand |
| `es/ballena.svg` | a whale with a spout, drawn by hand |

## Licenses

- **Audio:** made for this project with [Piper](https://github.com/OHF-Voice/piper1-gpl)
  text to speech, from voices whose training data has no license restrictions:
  `en_US-ljspeech-medium` (LJ Speech, public domain) and `es_ES-davefx-medium` (CC0).
- **Pictures:** SVGs written by hand for this project.

## Adding one

- Audio: Piper with one of the voices above, silence trimmed, then MP3 (`sox`, `lame`).
  Avoid voices with an attribution or non-commercial dataset license (check each voice's
  `MODEL_CARD`). Listen to it once by ear.
- Pictures: a few flat shapes, no text, readable at the size of a game card. The image
  game asks "what is this?", so show the thing itself and nothing that names it.
- Name the file after the fixture word, lowercase, `[a-z]+` only (the URL check in
  `words/schemas.py` accepts nothing else).
