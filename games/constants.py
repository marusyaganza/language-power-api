GAME_TYPE_REQUIREMENTS = {
    "audio": {"requires_audio": True},
    "select_def": {},
    "select_word": {},
    "type_word": {},
    "image": {"requires_image": True},
    "gender": {"requires_gender": True},
}

GAME_ANSWER_TYPES = {
    "audio": "typed",
    "select_def": "choice",
    "select_word": "choice",
    "type_word": "typed",
    "image": "typed",
    "gender": "gender",  # "masculine" / "feminine" / "both", with partial credit
}

# Shown as the heading of a game, above the question (never joined to it).
GAME_TASKS = {
    "select_def": "Pick the meaning of this word",
    "select_word": "Pick the word that matches this meaning",
    "type_word": "Type the word that matches this meaning",
    "audio": "Type the word you hear",
    "image": "Type the word for this picture",
    "gender": "Pick this noun's gender",
}
# Spaced-repetition presets a user can pick from. "recommended" is what users
# get until they change their settings; keep it equal to the defaults of
# games.spaced_repetition.SpacedRepetitionConfig.
GAME_SETTINGS_PRESETS = [
    {
        "id": "recommended",
        "title": "Recommended",
        "description": "A balanced schedule for steady daily practice: new words come back "
        "after 15 minutes, a day and 6 days before they are considered learned.",
        "settings": {"learning_steps_minutes": [15, 1440, 8640], "graduating_interval_days": 6, "strict_mode": False},
    },
    {
        "id": "intensive",
        "title": "Intensive",
        "description": "More frequent reviews for fast progress, e.g. before an exam or a trip. "
        "Forgetting a learned word sends it back to the start.",
        "settings": {"learning_steps_minutes": [15, 240, 1440], "graduating_interval_days": 3, "strict_mode": True},
    },
    {
        "id": "relaxed",
        "title": "Relaxed",
        "description": "Fewer, more spaced-out reviews for casual learners who practice a few times a week.",
        "settings": {"learning_steps_minutes": [1440, 4320], "graduating_interval_days": 7, "strict_mode": False},
    },
]
