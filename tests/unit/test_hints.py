# tests/unit/test_hints.py
import pytest

from games.hints import BLANK, hidden_definitions, hide_word


@pytest.mark.parametrize(
    ("text", "name", "stems", "expected"),
    [
        ("the heart of the matter", "heart", [], f"the {BLANK} of the matter"),
        ("Heart and HEART", "heart", [], f"{BLANK} and {BLANK}"),
        # Whole words only: "hearth" is a different word.
        ("sitting by the hearth", "heart", [], "sitting by the hearth"),
        # Stems are hidden too.
        ("two hearts beat", "heart", ["hearts"], f"two {BLANK} beat"),
        # The longer form wins, so a phrase stem becomes one blank.
        ("learn it by heart", "heart", ["by heart"], f"learn it {BLANK}"),
        # Next to non-word characters, where \b would fail.
        ("¡sea! dijo", "sea", [], f"¡{BLANK}! dijo"),
        # Regex characters in a form are matched literally.
        ("c++ code", "c++", [], f"{BLANK} code"),
        # Blank forms are ignored instead of matching everywhere.
        ("nothing to hide", "", ["  "], "nothing to hide"),
    ],
)
def test_hide_word(text, name, stems, expected):
    assert hide_word(text, name, stems) == expected


def test_hidden_definitions_hides_the_word_in_each():
    defs = ["casa grande", "una casa", "a building"]
    assert hidden_definitions("casa", [], defs) == [f"{BLANK} grande", f"una {BLANK}", "a building"]
