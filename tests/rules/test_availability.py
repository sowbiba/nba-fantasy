import json
import pathlib
from datetime import date

import pytest

from engine.rules.availability import (
    Availability, PickRow, SecondChance, SeriesRow, is_available,
)

CASES = json.loads((pathlib.Path(__file__).parent / "availability_cases.json").read_text())


def _d(s):
    return date.fromisoformat(s) if s else None


def run_case(case) -> Availability:
    return is_available(
        player_id=case["player_id"],
        player_team=case["player_team"],
        night=_d(case["night"]),
        season=case["season"],
        mode=case["mode"],
        picks=[PickRow(p["id"], p["player_id"], _d(p["date"]), p["mode"], p["season"]) for p in case["picks"]],
        second_chances=[
            SecondChance(s["pick_id"], s["player_id"], _d(s["bought_on"]), _d(s["expires_on"]))
            for s in case["second_chances"]
        ],
        series=[SeriesRow(**s) for s in case["series"]],
        exclude_pick_id=case["exclude_pick_id"],
    )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_disponibilite(case):
    exp = case["expected"]
    assert run_case(case) == Availability(exp["ok"], _d(exp["available_from"]), exp["reason"])
