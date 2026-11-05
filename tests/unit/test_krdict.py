# tests/unit/test_krdict.py
"""Turning rows of the imported Korean dictionary into entries.

The rows are made up for these tests, in the shape `find_entries` returns.
"""

from dictionary.entry import DictionaryExample
from dictionary.ko.ko import KoreanDictionaryProvider


def row(word, *, key="1", unit="단어", pos="명사", pronunciation=None, forms=(), senses=None):
    return {
        "key": key,
        "word": word,
        "unit": unit,
        "homonym_number": 0,
        "pos": pos,
        "level": None,
        "pronunciation": pronunciation,
        "forms": list(forms),
        "senses": senses or [{"en": "made up", "en_def": None, "examples": []}],
    }


def parse(*rows, suggestions=()):
    return KoreanDictionaryProvider()._parse({"entries": list(rows), "suggestions": list(suggestions)})


def test_a_word_becomes_an_entry():
    [entry] = parse(
        row(
            "가게",
            key="17",
            pronunciation="가ː게",
            senses=[
                {"en": "shop; store", "en_def": "A made-up definition.", "examples": ["가게 하나.", "가게 둘."]},
                {"en": "stall", "en_def": None, "examples": ["가게 셋."]},
            ],
        )
    ).words

    assert (entry.uuid, entry.name, entry.language, entry.fl) == ("17", "가게", "ko", "noun")
    assert entry.defs == ["shop; store", "stall"]
    assert entry.transcription == "가ː게"
    assert entry.examples == [
        DictionaryExample("가게 하나."),
        DictionaryExample("가게 둘."),
        DictionaryExample("가게 셋."),
    ]
    assert (entry.audio_url, entry.img_url, entry.gender, entry.offensive) == (None, None, None, False)


def test_entries_keep_the_order_they_come_in_and_repeated_meanings_are_dropped():
    words = parse(
        row("가다", key="1", pos="동사", senses=[{"en": "go", "en_def": None, "examples": []}] * 2),
        row("가다", key="2", pos="보조 동사"),
    ).words

    assert [(w.uuid, w.fl, w.defs) for w in words] == [("1", "verb", ["go"]), ("2", "auxiliary verb", ["made up"])]


def test_an_unknown_part_of_speech_is_shown_as_it_is():
    [entry] = parse(row("말", pos="새 품사")).words

    assert entry.fl == "새 품사"


def test_an_idiom_is_named_as_one_would_type_it_and_found_by_every_spelling():
    [entry] = parse(
        row(
            "진땀(을) 빼다[흘리다]",
            key="5:진땀(을) 빼다[흘리다]",
            unit="관용구",
            pos="품사 없음",
            forms=["진땀을 흘리다", "진땀 빼다", "진땀 흘리다"],
        )
    ).words

    assert (entry.uuid, entry.name, entry.fl) == ("5:진땀(을) 빼다[흘리다]", "진땀을 빼다", "idiom")
    assert entry.stems == ["진땀(을) 빼다[흘리다]", "진땀을 흘리다", "진땀 빼다", "진땀 흘리다"]


def test_a_grammar_pattern_shows_its_english_definition_and_romanization():
    [entry] = parse(
        row(
            "-거든요",
            unit="문법‧표현",
            pos="품사 없음",
            senses=[{"en": "-geodeunnyo", "en_def": "A made-up explanation of the ending.", "examples": []}],
        )
    ).words

    assert (entry.name, entry.fl, entry.defs, entry.transcription) == (
        "-거든요",
        "grammar pattern",
        ["A made-up explanation of the ending."],
        "-geodeunnyo",
    )


def test_suggestions_come_through_when_nothing_matched():
    result = parse(suggestions=["가게", "가구"])

    assert (result.words, result.suggestions) == ([], ["가게", "가구"])
