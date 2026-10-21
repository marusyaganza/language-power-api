# tests/unit/test_mw.py
import pytest

from dictionary.helpers.mw import extract_gender


@pytest.mark.parametrize(
    ("fl", "expected"),
    [
        ("masculine noun", "masculine"),
        ("feminine noun", "feminine"),
        # "el/la ecologista": one entry, both genders.
        ("masculine or feminine noun", "both"),
        ("noun", None),
        ("transitive verb", None),
        ("Masculine Noun", "masculine"),
        (None, None),
    ],
)
def test_extract_gender(fl, expected):
    assert extract_gender(fl) == expected
