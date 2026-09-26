from datetime import date

import pytest

from engine.config import env
from engine.rules.game_types import previous_season, season_for_date


@pytest.mark.parametrize("d,expected", [
    (date(2026, 10, 20), "2026-27"),
    (date(2026, 9, 1), "2026-27"),
    (date(2027, 4, 15), "2026-27"),
    (date(2026, 8, 31), "2025-26"),
])
def test_season_for_date(d, expected):
    assert season_for_date(d) == expected


def test_previous_season():
    assert previous_season("2026-27") == "2025-26"
    assert previous_season("2000-01") == "1999-00"


def test_env_absent(monkeypatch):
    monkeypatch.delenv("TTFL_VARIABLE_INEXISTANTE", raising=False)
    with pytest.raises(RuntimeError, match="TTFL_VARIABLE_INEXISTANTE"):
        env("TTFL_VARIABLE_INEXISTANTE")


def test_env_present(monkeypatch):
    monkeypatch.setenv("TTFL_TEST_VAR", "ok")
    assert env("TTFL_TEST_VAR") == "ok"
