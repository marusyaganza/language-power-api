"""docs/configuration.md lists every setting."""

import re
from pathlib import Path

from settings import Settings

CONFIGURATION = Path(__file__).resolve().parents[2] / "docs" / "configuration.md"


def test_every_setting_is_documented():
    rows = [line for line in CONFIGURATION.read_text(encoding="utf-8").splitlines() if line.startswith("| `")]
    documented = {name for row in rows for name in re.findall(r"`([A-Z][A-Z0-9_]+)`", row.split("|")[1])}
    missing = sorted(name.upper() for name in Settings.model_fields if name.upper() not in documented)
    assert missing == [], f"add to docs/configuration.md: {missing}"
