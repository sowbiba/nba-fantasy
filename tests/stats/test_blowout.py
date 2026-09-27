"""Facteur « écart de force » (L3a §2) : calibration, bornes, application."""
from datetime import date, timedelta

import pytest

from engine.stats.blowout import (
    BENCH_SLOPE_BOUNDS,
    FACTOR_BOUNDS,
    NEUTRAL,
    STARTER_SLOPE_BOUNDS,
    BlowoutModel,
    calibrate,
    factor,
)
from engine.stats.profile import GameLog, PlayerProfile
from engine.stats.projection import GameContext, project

SEASON = "2025-26"
D0 = date(2025, 11, 1)
BEFORE = date(2026, 3, 1)
# Écarts finaux multiples de 2 : minutes entières avec 0,5 min par point.
MARGINS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]


def _game(i, d, margin, status="final"):
    return {"id": f"g{i}", "date": d.isoformat(), "home_team": "AAA", "away_team": "BBB",
            "game_type": "regular", "status": status, "season": SEASON,
            "home_score": 100 + margin, "away_score": 100}


def _synthetic(starter_per_pt=0.5, bench_per_pt=0.5, threshold=10, reps=3):
    """Titulaire (base 40 min) : −starter_per_pt min par point au-delà du
    seuil ; remplaçant (base 20 min) : +bench_per_pt."""
    games, logs = [], []
    i = 0
    for _ in range(reps):
        for m in MARGINS:
            d = D0 + timedelta(days=i)
            games.append(_game(i, d, m))
            excess = max(0, m - threshold)
            logs.append(GameLog(1, f"g{i}", d, SEASON, "AAA", int(40 - starter_per_pt * excess), 50, True))
            logs.append(GameLog(2, f"g{i}", d, SEASON, "AAA", int(20 + bench_per_pt * excess), 20, True))
            i += 1
    return games, logs


def _avg(logs, pid):
    mins = [l.minutes for l in logs if l.player_id == pid]
    return sum(mins) / len(mins)


def test_calibration_retrouve_une_pente_connue_et_son_seuil():
    games, logs = _synthetic()
    model = calibrate(logs, games, BEFORE)
    # ratio = minutes / moyenne : pente en ratio = pente en minutes / moyenne.
    assert model.starter_threshold == 10
    assert model.bench_threshold == 10
    assert model.starter_slope == pytest.approx(0.5 / _avg(logs, 1))
    assert model.bench_slope == pytest.approx(0.5 / _avg(logs, 2))


def test_calibration_pentes_bornees():
    games, logs = _synthetic(starter_per_pt=1.0, bench_per_pt=1.0)   # effets énormes
    model = calibrate(logs, games, BEFORE)
    assert model.starter_slope == STARTER_SLOPE_BOUNDS[1]
    assert model.bench_slope == BENCH_SLOPE_BOUNDS[1]
    # Effet inverse (titulaires jouent PLUS dans les gros écarts) → borné à 0.
    games, logs = _synthetic(starter_per_pt=-0.5, bench_per_pt=-0.5)
    model = calibrate(logs, games, BEFORE)
    assert model.starter_slope == 0.0
    assert model.bench_slope == 0.0


def test_calibration_sans_donnees_modele_neutre():
    assert calibrate([], [], BEFORE) == NEUTRAL
    games, logs = _synthetic()
    # Tous les matchs sont après `before` : rien d'exploitable.
    assert calibrate(logs, games, D0) == NEUTRAL


def test_calibration_ignore_les_dnp_et_les_matchs_non_termines():
    games, logs = _synthetic()
    base = calibrate(logs, games, BEFORE)
    # DNP (0 min) : absence, pas un effet d'écart → ignoré, modèle identique.
    assert calibrate(logs + [GameLog(1, "g0", D0, SEASON, "AAA", 0, 0, True)], games, BEFORE) == base
    # Match non terminé (reporté) avec un « score » de 60 pts d'écart et des
    # minutes hors tendance : s'il était compté, l'ajustement ne serait plus
    # parfait. Ses logs comptent dans la moyenne du joueur, pas dans la pente.
    d = D0 + timedelta(days=80)
    odd = {**_game(999, d, 60), "status": "scheduled"}
    odd_logs = [GameLog(1, "g999", d, SEASON, "AAA", 40, 50, True), GameLog(2, "g999", d, SEASON, "AAA", 20, 20, True)]
    model = calibrate(logs + odd_logs, games + [odd], BEFORE)
    assert model.starter_threshold == 10
    assert model.starter_slope == pytest.approx(0.5 / _avg(logs + odd_logs, 1))
    assert model.bench_slope == pytest.approx(0.5 / _avg(logs + odd_logs, 2))


def test_calibration_aucun_log_ni_match_du_jour_d():
    """Un match (score et logs) du soir D ne change rien à la calibration
    pour D : seuls les logs ET matchs de date < D comptent."""
    games, logs = _synthetic()
    d = BEFORE
    base = calibrate(logs, games, d)
    blowout_game = _game(1000, d, 60)
    blowout_logs = [GameLog(1, "g1000", d, SEASON, "AAA", 10, 5, True),
                    GameLog(2, "g1000", d, SEASON, "AAA", 48, 60, True)]
    assert calibrate(logs + blowout_logs, games + [blowout_game], d) == base


def test_factor_titulaire_baisse_remplacant_monte_au_dela_du_seuil():
    model = BlowoutModel(0.01, 5.0, 0.02, 5.0)
    assert factor(model, 3.0, True) == 1.0
    assert factor(model, 3.0, False) == 1.0
    assert factor(model, 12.0, True) == pytest.approx(1 - 0.01 * 7)
    assert factor(model, -12.0, True) == pytest.approx(1 - 0.01 * 7)   # signe indifférent
    assert factor(model, 12.0, False) == pytest.approx(1 + 0.02 * 7)


def test_factor_borne():
    model = BlowoutModel(0.02, 0.0, 0.03, 0.0)
    assert factor(model, 40.0, True) == FACTOR_BOUNDS[0]
    assert factor(model, 40.0, False) == FACTOR_BOUNDS[1]


def test_project_sans_modele_ignore_l_ecart_attendu():
    prof = PlayerProfile(1, 1.5, 34.0, 20, 8.0, 0.95)
    plain = GameContext("BOS", True, 1, 1.0)
    with_margin = GameContext("BOS", True, 1, 1.0, expected_margin=20.0)
    assert project(prof, with_margin) == project(prof, plain)
    model = BlowoutModel(0.01, 5.0, 0.02, 5.0)
    assert project(prof, plain, model) == project(prof, plain)        # écart inconnu → aucun facteur
    assert project(prof, with_margin, model) == pytest.approx(project(prof, plain) * (1 - 0.01 * 15))
    bench = PlayerProfile(2, 1.0, 18.0, 20, 6.0, 0.95)
    assert project(bench, with_margin, model) == pytest.approx(project(bench, plain) * 1.15)   # 1 + 0,02×15 borné
