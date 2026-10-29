# Games API

How the vocabulary games work, from the point of view of a client of this API.
It covers what each endpoint does, what each game sends and expects, and the
rules behind scheduling and scoring. Implementation details are left out.

All game endpoints require a logged-in user (the session cookie set by
signup or login). Every game uses only the logged-in user's own saved words.

## The games

| Game type | Title | Question | Player answers by | Words it can use |
|---|---|---|---|---|
| `select_def` | Pick the Meaning | The word | Picking its definition from 4 options | All |
| `select_word` | Pick the Word | Up to 3 definitions | Picking the word from 4 options | All |
| `type_word` | Type the Word | Up to 3 definitions | Typing the word | All |
| `audio` | Listen & Type | Pronunciation audio URL | Typing the word | Words with audio |
| `image` | Name the Picture | Image URL | Typing the word | Words with an image |
| `gender` | Noun Gender | The word (a noun) | Ticking masculine, feminine, or both | Words with a gender (Spanish only) |

Images come from the English dictionary, which has them for some words only.
The Spanish dictionary has none, so a Spanish word has an image only if the
user adds one when editing the word.

The games are listed from easiest to hardest: first recognizing a word among
options, then recalling it without help.

A game session has 5 questions by default. If the user has fewer eligible
words, the session has fewer questions.

## The flow of a game

1. **List the games** for a language: `GET /games?language=es`
2. **Start a session**: `POST /games/{game_id}/sessions`
3. **Answer each question**: `POST /games/sessions/{session_id}/answers` (once per question)
4. **Show the result**: `POST /games/sessions/{session_id}/result`

Starting and finishing change state, so every step after the list is a
`POST`.

The player can stop at any time. Requesting the result ends the session
early (see [Finishing early](#finishing-early)).

## 1. List games: `GET /games?language={lang}`

Returns the games offered for the language, in display order, with word
counts for each:

```json
[
  {
    "id": 27,
    "slug": "type-the-word",
    "title": "Type the Word",
    "description": "Read a definition and type the word from memory.",
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

## 2. Start a session: `POST /games/{game_id}/sessions`

Each call creates a new session.

```json
{ "language": "es", "mode": "spaced", "new_words_first": false }
```

| Field | Values | Default | Meaning |
|---|---|---|---|
| `language` | `en`, `es` | required | Which saved words to use |
| `mode` | `spaced`, `review` | `spaced` | See [Modes](#modes) |
| `new_words_first` | `true`, `false` | `false` | Put words never practiced in this game before the others |

Response (201):

```json
{
  "task": "Type the word that matches this meaning",
  "session_id": "2f56b64e-567c-49b6-aafa-aca946bf37c4",
  "questions": [
    {
      "id": 67,
      "question": ["a trip from one place to another, usually a long one", "to go on a ___"],
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

- `task` is the instruction to show as the game's heading, with the
  question below it. Never join the two.
- `session_id` identifies the session in the answer and result URLs.
- `id` of a question is the word's id. Send it back as `word_id` when
  answering.
- `question` is a list of strings (definitions) or a single string (a word,
  or an audio/image URL), depending on the game.
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
For example, "to go on a **journey**" becomes "to go on a ___".

### Options in the multiple-choice games

- There are 4 options, one of them correct, in random order.
- **Wrong options come from the user's own saved words.** No made-up words
  or definitions are used.
- No two options are the same, and only one is correct. Synonyms and words
  with the same spelling (e.g. "ser" the verb and "ser" the noun) are never
  offered together where both would fit.
- **Rarely, a question has fewer than 4 options**, when the user's words
  don't provide enough distinct ones. The client should handle 2–4 options.

## 3. Answer a question: `POST /games/sessions/{session_id}/answers`

```json
{ "word_id": 67, "answer": "jorney" }
```

What to send as `answer`:

| Game | `answer` |
|---|---|
| `type_word`, `audio`, `image` | What the player typed. Case and surrounding spaces don't matter. |
| `select_word`, `select_def` | **The option text exactly as received.** |
| `gender` | `"masculine"`, `"feminine"` or `"both"` (both boxes ticked). Nothing ticked can be sent as `""` and counts as wrong. |

Response:

```json
{ "grade": "close", "correct_answer": "journey", "session_complete": false }
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

## 4. Result: `POST /games/sessions/{session_id}/result`

Ends the session if it's still running and returns its result. No body.

```json
{
  "total_words": 6,
  "correct": 3,
  "close": 1,
  "wrong": 1,
  "unanswered": 1,
  "score_percent": 67
}
```

- **`score_percent` counts `close` answers as correct.** It is
  (correct + close) ÷ total words, rounded half up, so 1 of 6 gives 17%.
  Unanswered questions count against the score.
- `total_words` is every word in the session.

### Finishing early

Requesting the result ends the session, even if some questions are
unanswered. After that:

- no more answers are accepted (409);
- unanswered words are reported as `"unanswered"` and do not affect the
  word's practice schedule;
- the result can be requested again: the same call returns the same result,
  with no error.

## Modes

Progress is tracked per word and per game type. Practicing a word in the
audio game doesn't change when it is due in Type the Word.

### Spaced repetition (`mode=spaced`, the default)

Only due words are used. A word is due if it was never practiced in this
game, or its next review date has passed. The most overdue words come first.

### Review (`mode=review`)

All the user's words are used, starting with the ones practiced least
recently. Repeated review sessions therefore cycle through the vocabulary
rather than showing the same words again.

**Answering a word in review mode only changes its schedule if the word was
due anyway.** Extra practice can't push a word's next review further into
the future. The answer is still recorded, and it moves the word to the back
of the review order.

### New words (`new_words_first`)

Words never practiced in a game come after the others by default, and
before them with `new_words_first=true`. In both cases, new words are
picked in random order.

### How the schedule moves

Each user's schedule follows their [settings](#spaced-repetition-settings).
With the default ("Recommended") settings:

- **A new word** comes back after 15 minutes, then 1 day, then 6 days. A
  correct answer moves it a step forward. A wrong answer sends it back to
  the first step. A close answer repeats the current step.
- **After the last step the word "graduates"** and comes back after 6 days.
  From then on, a correct answer doubles the interval (up to 90 days). A
  close answer grows it a little. A wrong answer halves it (at least 1 day),
  or, in strict mode, sends the word back to the first learning step.

Progress is saved before the answer response is sent, so the next
`GET /games` already reflects the answer.

## Spaced repetition settings

Each user can change how their words are scheduled. The settings apply to
every game.

### Endpoints

- `GET /users/me/game-settings`: the user's settings. Users who never
  changed them get the "Recommended" preset.
- `PUT /users/me/game-settings`: replace them. The body has the three
  settings and returns the same shape as `GET`.
- `GET /users/me/game-settings/presets`: the presets to offer, the first
  being the default.

```json
{
  "learning_steps_minutes": [15, 1440, 8640],
  "graduating_interval_days": 6,
  "strict_mode": false,
  "preset": "recommended"
}
```

- `preset` is the id of the preset the values match, or `"custom"`. It is
  only returned, never sent. To apply a preset, send its `settings`.

Values are checked, and anything invalid is rejected with 422:

| Setting | Allowed values |
|---|---|
| `learning_steps_minutes` | 1 to 5 steps, each between 1 minute and 90 days, each longer than the one before |
| `graduating_interval_days` | Whole days from 1 to 90, and not shorter than the last learning step |
| `strict_mode` | `true` or `false` |

### Presets

| Preset | Learning steps | Graduating interval | Strict | For |
|---|---|---|---|---|
| Recommended | 15 min, 1 day, 6 days | 6 days | off | Steady daily practice |
| Intensive | 15 min, 4 hours, 1 day | 3 days | on | Fast progress, e.g. before an exam or a trip |
| Relaxed | 1 day, 3 days | 7 days | off | Practicing a few times a week |

Each preset comes with a `title` and a `description` to show.

### When new settings take effect

**Changing the settings never moves a review that's already scheduled.** Each
word follows the new settings from its next answer on. If the user removes
learning steps, a word on a removed step continues from the last remaining
one.

## Session lifetime

- A running session expires 20 minutes after its last activity: when it
  was started, or its last answer. Each answer gives it another 20 minutes.
- Once a session is finished (every question answered, or the result
  requested), it is kept for 1 hour so the result can still be read.
- **An expired session is deleted.** Answering it or asking for its result
  returns 404, the same as for a session that never existed. Every answer
  was already saved as learning progress, but the session's result is gone.
  Tell the player the game timed out and offer a new one.
- **A session can only be used by the user who started it.** Anyone else gets
  404, as if it didn't exist.

## Errors

| Status | When |
|---|---|
| 401 | Not logged in, or the session cookie expired. |
| 404 | Game doesn't exist. Session expired, never existed, or belongs to another user. The word isn't part of the session. |
| 409 | Question already answered. Session already finished. Starting `select_word`/`select_def` with fewer words than `min_word_count`. |
| 422 | Invalid request values, e.g. a session started without `language`, or game settings out of range. |
| 501 | The game exists but can't be played yet. All six games above are playable. |

Errors have the shape `{"detail": "<message>"}`.

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
- **Spaced repetition settings belong to the user, not the game.** Games are
  shared by all users, and one set of settings keeps the settings screen
  simple. Only three settings are exposed: the growth factors and the
  90-day limit stay fixed, because they are hard to explain and easy to set
  badly.
- **Settings changes can't break scheduling.** Invalid values are rejected
  when saved. Words keep working when steps are removed. If a stored value
  is ever invalid, the defaults are used instead of failing.
- **Starting and finishing a session are `POST`s.** Both change state:
  starting creates a session, and asking for the result ends it. A `GET` must
  be safe to repeat (RFC 9110), and clients and proxies may retry or prefetch
  it. The result call is still idempotent, so a client can retry it safely.
- **Sessions expire after 20 minutes without an answer, not 20 minutes after
  they start.** A player who is still answering is never cut off; an
  abandoned session is cleaned up by Redis on its own.
- **Finishing early is allowed.** A player in a hurry can stop. Skipped words
  keep their schedule.
