# Games API

How the vocabulary games work, from the point of view of a client of this API.
It covers what each endpoint does, what each game sends and expects, and the
rules behind scheduling and scoring. Implementation details are left out.

All game endpoints require a logged-in user (the session cookie set by
`/auth/login`). Every game uses only the logged-in user's own saved words.

---

## The games

| Game type | Title | Question | Player answers by | Words it can use |
|---|---|---|---|---|
| `type_word` | WordRecall | Up to 3 definitions | Typing the word | All |
| `audio` | WordEcho | Pronunciation audio URL | Typing the word | Words with audio |
| `image` | PictureWord Blitz | Image URL | Typing the word | Words with an image |
| `select_word` | Definify | Up to 3 definitions | Picking the word from 4 options | All |
| `select_def` | LexiSense | The word | Picking its definition from 4 options | All |
| `gender` | GenderWord Challenge | The word (a noun) | Ticking masculine, feminine, or both | Words with a gender (Spanish only) |

A game session has 5 questions by default. If the user has fewer eligible
words, the session has fewer questions.

---

## The flow of a game

1. **List the games** for a language: `GET /games?language=es`
2. **Start a session**: `GET /games/{game_id}?language=es&mode=spaced`
3. **Answer each question**: `POST /games/{game_id}/answer` (once per question)
4. **Show the result**: `GET /games/result/{session_id}`

The player can stop at any time. Requesting the result ends the session
early (see [Finishing early](#finishing-early)).

---

## 1. List games: `GET /games?language={lang}`

Returns the games offered for the language, in display order, with word
counts for each:

```json
[
  {
    "id": 4,
    "slug": "word-recall",
    "title": "WordRecall",
    "description": "Type words matching given definitions...",
    "game_type": "type_word",
    "total_word_count": 40,
    "due_word_count": 3,
    "next_due_at": "2026-10-18T14:05:00Z",
    "min_word_count": 1
  }
]
```

- `total_word_count`: the user's words this game can use.
- `due_word_count`: how many of them are due for practice now. Words never
  practiced in this game count as due.
- `next_due_at`: when the next word that isn't due yet becomes due, or
  `null` if there is none. Use it for messages like "next word due in 2h".
- `min_word_count`: words needed to start this game. It is 4 for
  `select_word` and `select_def` (one word per option) and 1 for the others.

**Which games to enable is up to the client.** Both counts are always
returned, so the client can switch modes without another request:

- In spaced repetition mode, a game is playable when `due_word_count > 0`
  and `total_word_count >= min_word_count`.
- In review mode, a game is playable when `total_word_count >= min_word_count`
  (and above 0).

---

## 2. Start a session: `GET /games/{game_id}`

| Query parameter | Values | Default | Meaning |
|---|---|---|---|
| `language` | `en`, `es` | required | Which saved words to use |
| `mode` | `spaced`, `review` | `spaced` | See [Modes](#modes) |
| `new_words_first` | `true`, `false` | `false` | Put words never practiced in this game before the others |

Response:

```json
{
  "task": "Type a word that means ",
  "session_id": "2f56b64e-567c-49b6-aafa-aca946bf37c4",
  "questions": [
    {
      "id": 67,
      "question": ["the organ in your chest that pumps blood", "the ___ thought of as the place where emotions are felt"],
      "options": null,
      "alt": null,
      "additional_info": {
        "audio_url": "https://...",
        "img_url": null,
        "examples": [{"text": "...", "translation": null}],
        "def": null
      }
    }
  ]
}
```

- `task` is the instruction to show. Some tasks end with a space and are
  meant to be followed by the question (e.g. "Select a word that means ").
- `id` of a question is the word's id. Send it back as `word_id` when
  answering.
- `question` is a **list of strings** (definitions) or a **single string**
  (a word, or an audio/image URL), depending on the game.
- `options` is set for `select_word`, `select_def` and `gender`, and `null`
  otherwise.
- `alt` is set only in the `image` game (see [Broken images](#broken-images)).
- **The questions come in random order.**
- **If the user has no eligible words, the session has an empty `questions`
  list.** This is not an error.

### What each game sends

| Game | `question` | `options` | `additional_info` |
|---|---|---|---|
| `type_word` | definitions (list) | – | `audio_url`, `img_url`, `examples` |
| `audio` | audio URL | – | `img_url`, `examples`, `def`. `audio_url` is `null` (it is the question). |
| `image` | image URL | – | `audio_url`, `examples`, `def`. `img_url` is `null` (it is the question). Also sets `alt`. |
| `select_word` | definitions (list) | 4 words | `audio_url`, `img_url`, `examples` |
| `select_def` | the word | 4 definitions | `audio_url`, `img_url`, `examples` |
| `gender` | the word | `["masculine", "feminine"]` | `audio_url`, `img_url`, `examples`, `def` |

`def` is a sentence of the form `"ballena means whale"`.

### Broken images

The `image` game depends on an external image link, which can break. Each
`image` question carries `alt`: the word's first definition with the word
hidden, the same clue `type_word` would show first.

The client should preload the images when the session starts and listen for
the image's error event. If an image fails, show `alt` in its place with a
note such as "image unavailable". The game stays playable, and the user sees
which word needs a new image (the question `id` is the word id).

**Show `additional_info` only after the player has answered.** It often
contains the answer (examples use the word, `def` names it). It is sent
upfront so images and audio can be preloaded.

### Hidden words

Definitions often contain the word they define. Wherever definitions are
shown as clues or options, the word and its forms are replaced with `___`.
For example, "the **heart** thought of as…" becomes "the ___ thought of as…".

### Options in the multiple-choice games

- There are 4 options, one of them correct, in random order.
- **Wrong options come from the user's own saved words.** No made-up words
  or definitions are used.
- No two options are the same, and only one is correct. Synonyms and words
  with the same spelling (e.g. "ser" the verb and "ser" the noun) are never
  offered together where both would fit.
- **Rarely, a question has fewer than 4 options**, when the user's words
  don't provide enough distinct ones. The client should handle 2–4 options.

---

## 3. Answer a question: `POST /games/{game_id}/answer`

```json
{ "session_id": "2f56b64e-...", "word_id": 67, "answer": "heart" }
```

What to send as `answer`:

| Game | `answer` |
|---|---|
| `type_word`, `audio`, `image` | What the player typed. Case and surrounding spaces don't matter. |
| `select_word`, `select_def` | **The option text exactly as received.** |
| `gender` | `"masculine"`, `"feminine"` or `"both"` (both boxes ticked). Nothing ticked can be sent as `""` and counts as wrong. |

Response:

```json
{ "grade": "close", "correct_answer": "heart", "session_complete": false }
```

- `grade` is `correct`, `close` or `wrong`.
- `correct_answer` is the expected answer, sent whenever the grade isn't
  `correct`.
- `session_complete` becomes `true` once every question has been answered.

### Grades

| Grade | When |
|---|---|
| `correct` | Exactly right (typed answers ignore case and surrounding spaces). |
| `close` | Typed games: a small typo ("balena" for "ballena"). Gender game: only one gender ticked for a noun that takes both. |
| `wrong` | Anything else. In the gender game, ticking both for a noun with one gender is wrong. |

**Each question can be answered only once.** A second answer is rejected
(409), since the first response already showed the correct answer.

---

## 4. Result: `GET /games/result/{session_id}`

```json
{
  "total_words": 6,
  "correct": 3,
  "close": 1,
  "wrong": 1,
  "unanswered": 1,
  "score_percent": 67,
  "questions": [
    { "word_id": 67, "answer": "heart", "grade": "correct" },
    { "word_id": 68, "answer": "ballena", "grade": "unanswered" }
  ]
}
```

- **`score_percent` counts `close` answers as correct.** It is
  (correct + close) ÷ total words, rounded half up, so 1 of 6 gives 17%.
  Unanswered questions count against the score.
- `total_words` is every word in the session ("Learned words" on the
  result screen).
- `questions` lists each word with its expected answer and how it was graded,
  or `"unanswered"`.

### Finishing early

Requesting the result **ends the session**, even if some questions are
unanswered. After that:

- no more answers are accepted (409);
- unanswered words are reported as `"unanswered"` and **do not affect the
  word's practice schedule**;
- the result can be requested again and stays the same.

---

## Modes

Progress is tracked **per word and per game type**. Practicing a word in the
audio game doesn't change when it is due in WordRecall.

### Spaced repetition (`mode=spaced`, the default)

Only **due** words are used. A word is due if it was never practiced in this
game, or its next review date has passed. The most overdue words come first.

### Review (`mode=review`)

**All** the user's words are used, starting with the ones practiced least
recently. Repeated review sessions therefore cycle through the vocabulary
rather than showing the same words again.

**Answering a word in review mode only changes its schedule if the word was
due anyway.** Extra practice can't push a word's next review further into
the future. The answer is still recorded, and it moves the word to the back
of the review order.

### New words (`new_words_first`)

Words never practiced in a game come **after** the others by default, and
**before** them with `new_words_first=true`. In both cases, new words are
picked in random order.

### How the schedule moves

This is the learning schedule from Anki, as its users commonly configure it:

- **A new word** comes back after 15 minutes, then 1 day, then 6 days. A
  correct answer moves it a step forward. A wrong answer sends it back to
  15 minutes. A close answer repeats the current step.
- **After the 6-day step**, a correct answer doubles the interval (up to 90
  days). A close answer grows it a little. A wrong answer halves it (at least
  1 day).

Progress is saved just after the answer response is sent, so a `GET /games`
made at the same moment may not reflect the last answer yet.

---

## Session lifetime

- A session lasts **20 minutes** from the moment it starts. Answering doesn't
  extend it.
- Once a session is finished (every question answered, or the result
  requested), it is kept for **1 hour** so the result can still be read.
- An expired session returns 404.
- **A session can only be used by the user who started it.** Anyone else gets
  404, as if it didn't exist.

---

## Errors

| Status | When |
|---|---|
| 404 | Game doesn't exist. Session expired, never existed, or belongs to another user. The word isn't part of the session. |
| 400 | The session was started for a different game than the one in the answer URL. |
| 409 | Question already answered. Session already finished. Starting `select_word`/`select_def` with fewer words than `min_word_count`. |
| 501 | The game exists but can't be played yet. All six games above are playable. |

Errors have the shape `{"detail": "<message>"}`.

---

## Design decisions

The choices behind the rules above, and the reasons for them.

- **Close counts as correct in the score.** Language-learning apps
  (Duolingo, Memrise) accept typos so players aren't punished for slips. The
  schedule still treats `close` as partial: the word doesn't advance as fast
  as with a correct answer.
- **4 options, not 7.** Research on multiple-choice tests finds 3–4 options
  as informative as more, and 4 keeps reading short on a phone.
- **Wrong options are real words from the user's vocabulary**, not
  AI-generated fakes. Fakes are easy to spot, and real words give extra
  exposure to the user's own vocabulary.
- **Review mode doesn't reschedule words that aren't due.** Otherwise cramming
  would push words far into the future without real spacing.
- **Answers are graded on the server, and the expected answer never reaches
  the client before it answers.** Hints in `additional_info` are visible in
  dev tools. That trade-off is accepted: there are no leaderboards, so a
  player can only cheat themselves, and sending hints upfront lets media
  preload. If competitive features are added, hints would move into the
  answer response.
- **Broken images fall back to text, checked by the browser.** Checking
  image links on the server would slow every game start, could still pass
  when the browser can't show the image (hotlink blocking), and would make
  the server request user-supplied addresses. The browser knows for certain
  whether an image loaded, so it handles the fallback with `alt`.
- **Finishing early is allowed.** A player in a hurry can stop. Skipped words
  keep their schedule.
