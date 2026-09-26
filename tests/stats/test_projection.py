from datetime import date

import pytest

from engine.stats.profile import PlayerProfile
from engine.stats.projection import GameContext, project, rest_days

PROFILE = PlayerProfile(1, ttfl_per_min=1.5, exp_minutes=34.0, games_current=20, stddev=8.0, availability_rate=0.95)


def test_projection_domicile_defense_faible():
    ctx = GameContext("WAS", is_home=True, rest_days=1, opp_factor=1.10)
    assert project(PROFILE, ctx) == pytest.approx(51.0 * 1.10 * 1.02)


def test_projection_exterieur_back_to_back():
    ctx = GameContext("BOS", is_home=False, rest_days=0, opp_factor=0.90)
    assert project(PROFILE, ctx) == pytest.approx(51.0 * 0.90 * 0.98 * 0.96)


def test_rest_days():
    dates = {"DEN": [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 5)]}
    assert rest_days("DEN", date(2026, 11, 2), dates) == 0
    assert rest_days("DEN", date(2026, 11, 5), dates) == 2
    assert rest_days("DEN", date(2026, 11, 1), dates) is None
    assert rest_days("LAL", date(2026, 11, 1), dates) is None
