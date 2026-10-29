# tests/unit/test_readme.py
"""The README's environment variables table lists every setting."""

import re
from pathlib import Path

from settings import Settings

README = Path(__file__).resolve().parents[2] / "README.md"


def test_every_setting_is_in_the_environment_variables_table():
    rows = [line for line in README.read_text(encoding="utf-8").splitlines() if line.startswith("| `")]
    documented = {name for row in rows for name in re.findall(r"`([A-Z][A-Z0-9_]+)`", row.split("|")[1])}
    missing = sorted(name.upper() for name in Settings.model_fields if name.upper() not in documented)
    assert missing == [], f"add to the README's environment variables table: {missing}"
