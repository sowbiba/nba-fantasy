from datetime import date

import pytest

from engine.stats.profile import GameLog
from engine.stats.team_defense import defense_factors, opp_factor

GAMES = {"g1": {"home_team": "DEN", "away_team": "LAL"},
         "g2": {"home_team": "BOS", "away_team": "LAL"}}
POS = {1: "G", 2: "G", 3: "C"}


def _log(pid, gid, team, minutes, ttfl, season="2026-27"):
    return GameLog(pid, gid, date(2026, 11, 1), season, team, minutes, ttfl, team == GAMES[gid]["home_team"])


def test_equipe_qui_encaisse_plus_que_la_moyenne():
    # Les meneurs font 1.5 TTFL/min contre LAL (g1), 0.5 contre BOS (g2) ; moyenne ligue 1.0.
    current = [_log(1, "g1", "DEN", 30, 45), _log(2, "g2", "LAL", 30, 15)]
    f = defense_factors(current, [], GAMES, POS)
    # Sans prior, le facteur courant est fondu vers 1.0 : w = 1 / (1 + 15)
    w = 1 / 16
    assert f["LAL"]["G"] == pytest.approx(w * 1.5 + (1 - w) * 1.0)
    assert f["BOS"]["G"] == pytest.approx(w * 0.5 + (1 - w) * 1.0)


def test_prior_regresse_de_moitie_et_borne():
    prior = [_log(1, "g1", "DEN", 30, 90, "2025-26"), _log(2, "g2", "LAL", 30, 10, "2025-26")]
    f = defense_factors([], prior, GAMES, POS)
    # ratio prior LAL = 3.0/1.667 = 1.8 → régressé 1.4 → borné 1.15
    assert f["LAL"]["G"] == 1.15
    # ratio prior BOS = 0.333/1.667 = 0.2 → régressé 0.6 → borné 0.85
    assert f["BOS"]["G"] == 0.85


def test_log_d_une_equipe_absente_du_match_ignore():
    current = [_log(1, "g1", "DEN", 30, 45), GameLog(3, "g1", date(2026, 11, 1), "2026-27", "PHX", 30, 99, True)]
    f = defense_factors(current, [], GAMES, POS)
    assert "C" not in f.get("DEN", {}) or f["DEN"]["C"] == 1.0


def test_opp_factor_inconnu_neutre():
    assert opp_factor({}, "XXX", "G") == 1.0
    assert opp_factor({"LAL": {"G": 1.1}}, "LAL", "G-F") == 1.0
