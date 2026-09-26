from datetime import date, timedelta

import pytest

from engine.stats.profile import (
    GameLog, PRIOR_K, ROOKIE_MINUTES, ROOKIE_TTFL_PER_MIN, build_profile, prior_minutes, role_scales,
)


def _logs(pid, season, pairs, start=date(2026, 11, 30)):
    """pairs = [(minutes, ttfl)] du plus récent au plus ancien."""
    return [GameLog(pid, f"g{season}{i}", start - timedelta(days=2 * i), season, "DEN", m, t, True)
            for i, (m, t) in enumerate(pairs)]


def test_rookie_sans_historique():
    p = build_profile(9, [], [])
    assert (p.ttfl_per_min, p.exp_minutes, p.games_current) == (ROOKIE_TTFL_PER_MIN, ROOKIE_MINUTES, 0)


def test_debut_de_saison_prior_seul_avec_echelle_de_role():
    prior = _logs(1, "2025-26", [(30, 45), (30, 45)])
    p = build_profile(1, [], prior, role_scale=1.1)
    assert p.ttfl_per_min == pytest.approx(1.5)
    assert p.exp_minutes == pytest.approx(33.0)
    assert p.base == pytest.approx(49.5)


def test_melange_prior_et_saison_courante():
    prior = _logs(1, "2025-26", [(30, 30)] * 5)            # 1.0 TTFL/min, 30 min
    current = _logs(1, "2026-27", [(36, 72)] * PRIOR_K)    # 2.0 TTFL/min, 36 min
    p = build_profile(1, current, prior)
    assert p.ttfl_per_min == pytest.approx(1.5)            # w = 10 / (10 + 10)
    assert p.exp_minutes == pytest.approx(33.0)


def test_dnp_exclus_de_l_efficacite_mais_comptes_dans_la_presence():
    current = _logs(1, "2026-27", [(0, 0), (30, 60), (0, 0), (30, 60)])
    p = build_profile(1, current, [])
    w = 2 / (2 + PRIOR_K)
    assert p.ttfl_per_min == pytest.approx(w * 2.0 + (1 - w) * ROOKIE_TTFL_PER_MIN)
    assert p.availability_rate == pytest.approx(0.5)


def test_recence_le_match_recent_pese_plus():
    hot = build_profile(1, _logs(1, "2026-27", [(30, 90), (30, 30)]), [])
    cold = build_profile(1, _logs(1, "2026-27", [(30, 30), (30, 90)]), [])
    assert hot.ttfl_per_min > cold.ttfl_per_min


def test_presence_bornee():
    current = _logs(1, "2026-27", [(0, 0)] * 5 + [(30, 30)])
    assert build_profile(1, current, []).availability_rate == 0.5


def test_role_scales():
    minutes = {1: 36.0, 2: 34.0, 3: 30.0}
    rosters = {
        "DEN": [1, 2, 3] + list(range(10, 17)),   # 7 joueurs à 20 min → 100 + 140 = 240
        "BOS": [1, 2, 3],                          # 100 min : la star est partie → plafonné à 1.15
        "LAL": list(range(20, 30)),                # 10 × 30 min = 300 : encombré → plancher 0.85
    }
    minutes.update({i: 20.0 for i in range(10, 17)})
    minutes.update({i: 30.0 for i in range(20, 30)})
    scales = role_scales(minutes, rosters)
    assert scales["DEN"] == pytest.approx(1.0)
    assert scales["BOS"] == 1.15
    assert scales["LAL"] == 0.85


def test_prior_minutes_moyenne_des_matchs_joues():
    logs = _logs(1, "2025-26", [(30, 40), (0, 0), (34, 50)])
    assert prior_minutes(logs) == {1: 32.0}
