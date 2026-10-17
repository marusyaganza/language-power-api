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

GAME_TASKS = {
    "audio": "Type the word that you've heard",
    "select_def": "Select a definition that means ",
    "select_word": "Select a word that means ",
    "type_word": "Type a word that means ",
    "image": "Type the name of the object shown in the picture.",
    "gender": "Pick the Correct Gender",
}