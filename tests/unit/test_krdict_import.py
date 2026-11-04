# tests/unit/test_krdict_import.py
"""Reading the Korean dictionary's XML download into rows.

The XML is made up for these tests, in the download's shape; no text comes
from the dictionary.
"""

import pytest

from dictionary.ko.import_krdict import ImportStats, KrdictFormatError, read_entries

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<LexicalResource dtdVersion="16"><Lexicon>'
FOOTER = "</Lexicon></LexicalResource>"


def feat(att, val):
    return f'<feat att="{att}" val="{val}" />'


def english(lemma, definition=None):
    parts = [feat("language", "영어"), feat("lemma", lemma)]
    if definition:
        parts.append(feat("definition", definition))
    return f"<Equivalent>{''.join(parts)}</Equivalent>"


def sense(*children):
    return f'<Sense att="id" val="1">{feat("definition", "만든 뜻.")}{"".join(children)}</Sense>'


def example(kind, *texts):
    return f"<SenseExample>{feat('type', kind)}{''.join(feat('example', t) for t in texts)}</SenseExample>"


def entry(entry_id, word, *children, unit="단어", pos="명사", level="초급", homonym="0"):
    feats = [feat("lexicalUnit", unit)]
    if homonym is not None:
        feats.insert(0, feat("homonym_number", homonym))
    if pos is not None:
        feats.append(feat("partOfSpeech", pos))
    lemma = f"<Lemma>{feat('writtenForm', word)}</Lemma>"
    level_feat = feat("vocabularyLevel", level) if level is not None else ""
    return (
        f'<LexicalEntry att="id" val="{entry_id}">{"".join(feats)}{lemma}{level_feat}{"".join(children)}</LexicalEntry>'
    )


def read(tmp_path, *entries):
    path = tmp_path / "001.xml"
    path.write_text(HEADER + "".join(entries) + FOOTER, encoding="utf-8")
    stats = ImportStats()
    return list(read_entries(path, stats)), stats


def test_a_word_becomes_a_row(tmp_path):
    pronunciation = f"<WordForm>{feat('type', '발음')}{feat('pronunciation', '가ː게')}{feat('sound', 'https://x.invalid/a.wav')}</WordForm>"
    [row], _ = read(
        tmp_path,
        entry(
            901,
            "가게",
            pronunciation,
            sense(english("shop", "A made-up place to buy things.")),
            sense(english("stall")),
        ),
    )

    assert row == {
        "key": "901",
        "id": 901,
        "word": "가게",
        "unit": "단어",
        "homonym_number": 0,
        "pos": "명사",
        "level": "초급",
        "pronunciation": "가ː게",
        "forms": [],
        "senses": [
            {"en": "shop", "en_def": "A made-up place to buy things.", "examples": []},
            {"en": "stall", "en_def": None, "examples": []},
        ],
    }


def test_idioms_proverbs_and_grammar_patterns_are_kept_with_their_kind(tmp_path):
    rows, stats = read(
        tmp_path,
        entry(902, "가게(를) 보다", sense(english("mind the shop")), unit="관용구", pos=None, level=None, homonym=None),
        entry(
            903,
            "-거든요",
            sense(english("-geodeunnyo", "A made-up grammar meaning.")),
            unit="문법‧표현",
            pos="품사 없음",
        ),
        entry(904, "무엇", sense(english("something")), unit="새 종류"),
    )

    assert [(row["word"], row["unit"], row["pos"], row["level"]) for row in rows] == [
        ("가게(를) 보다", "관용구", "품사 없음", None),
        ("-거든요", "문법‧표현", "품사 없음", "초급"),
    ]
    assert stats.skipped == {"unknown kind '새 종류'": 1}


@pytest.mark.parametrize(
    ("headword", "spellings"),
    [
        ("가게(를) 보다", ["가게를 보다", "가게 보다"]),
        ("눈이 맞다[통하다/뜨다]", ["눈이 맞다", "눈이 통하다", "눈이 뜨다"]),
        ("집에서[집에 가서] 쉬다", ["집에서 쉬다", "집에 가서 쉬다"]),
        ("말이[말도] 많다[적다]", ["말이 많다", "말이 적다", "말도 많다", "말도 적다"]),
        ("-거든요", ["거든요"]),
    ],
    ids=["optional part", "alternatives", "alternative with a space", "two brackets", "grammar pattern"],
)
def test_idioms_and_grammar_patterns_can_be_found_without_their_notation(tmp_path, headword, spellings):
    [row], _ = read(tmp_path, entry(905, headword, sense(english("made up")), unit="관용구"))

    assert row["forms"] == spellings


def test_meanings_without_english_are_dropped_and_so_are_entries_left_without_any(tmp_path):
    no_english = (
        '<Sense att="id" val="2"><Equivalent>'
        + feat("language", "일본어")
        + feat("lemma", "x")
        + "</Equivalent></Sense>"
    )
    rows, stats = read(
        tmp_path,
        entry(904, "나무", sense(english("tree")), no_english),
        entry(905, "가-", no_english, pos="품사 없음", level="없음"),
    )

    assert [(row["word"], [s["en"] for s in row["senses"]]) for row in rows] == [("나무", ["tree"])]
    assert stats.skipped == {"no English meaning": 1}


def test_examples_are_sentences_first_then_phrases_at_most_three_and_no_dialogues(tmp_path):
    examples = (
        example("구", "구 하나."),
        example("대화", "가: 질문?", "나: 대답."),
        example("문장", "문장 하나."),
        example("구", "구 둘."),
        example("문장", "문장 둘."),
    )
    [row], _ = read(tmp_path, entry(906, "말", sense(english("word"), *examples)))

    assert row["senses"][0]["examples"] == ["문장 하나.", "문장 둘.", "구 하나."]


def test_conjugated_and_contracted_forms_are_kept_once(tmp_path):
    def conjugated(written, contraction=None):
        nested = ""
        if contraction:
            nested = (
                f"<FormRepresentation>{feat('type', '준말')}{feat('writtenForm', contraction)}</FormRepresentation>"
            )
        return f"<WordForm>{feat('type', '활용')}{feat('writtenForm', written)}{nested}</WordForm>"

    [row], _ = read(
        tmp_path,
        entry(
            907,
            "하다",
            conjugated("하여", "해"),
            conjugated("하니"),
            conjugated("해"),
            sense(english("do")),
            pos="동사",
        ),
    )

    assert row["forms"] == ["하여", "해", "하니"]


def test_no_level_or_homonym_number_and_an_empty_pronunciation_become_defaults(tmp_path):
    empty_pronunciation = f'<WordForm>{feat("type", "발음")}<feat att="pronunciation" /></WordForm>'
    [row], _ = read(
        tmp_path, entry(908, "물", empty_pronunciation, sense(english("water")), level="없음", homonym=None)
    )

    assert (row["level"], row["homonym_number"], row["pronunciation"]) == (None, 0, None)


def test_control_characters_are_removed_before_parsing(tmp_path):
    # A backspace, as found inside a translation in the real download.
    [row], stats = read(tmp_path, entry(909, "불", sense(english("fire\x08"))))

    assert row["senses"][0]["en"] == "fire"
    assert stats.invalid_chars == 1


@pytest.mark.parametrize(
    "broken",
    [
        '<LexicalEntry att="id" val="">' + feat("lexicalUnit", "단어") + "</LexicalEntry>",
        '<LexicalEntry att="id" val="910">' + feat("lexicalUnit", "단어") + "</LexicalEntry>",
    ],
    ids=["no id", "no word"],
)
def test_an_entry_without_id_or_word_stops_the_import(tmp_path, broken):
    with pytest.raises(KrdictFormatError):
        read(tmp_path, broken)
