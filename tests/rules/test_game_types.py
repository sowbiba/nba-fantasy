import json
import pathlib
from datetime import date

import pytest

from engine.rules.game_types import game_type_of, is_eligible, mode_of, season_of

CASES = json.loads((pathlib.Path(__file__).parent / "game_type_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_type_et_saison(case):
    d = date.fromisoformat(case["date"])
    assert game_type_of(case["id"]) == case["game_type"]
    assert season_of(case["id"], d) == case["season"]


@pytest.mark.parametrize("game_type,eligible", [
    ("regular", True), ("cup_final", True), ("playoffs", True),
    ("preseason", False), ("playin", False), ("allstar", False), ("unknown", False),
])
def test_eligibilite(game_type, eligible):
    assert is_eligible(game_type) is eligible


def test_mode():
    assert mode_of("playoffs") == "playoffs"
    assert mode_of("regular") == "regular"
    assert mode_of("cup_final") == "regular"
