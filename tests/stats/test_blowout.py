"""Facteur « écart de force » (L3a §2) : calibration, bornes, application."""
from datetime import date, timedelta

import pytest

from engine.stats.blowout import (
    BENCH_SLOPE_BOUNDS,
    FACTOR_BOUNDS,
    MIN_SAMPLE,
    NEUTRAL,
    STARTER_SLOPE_BOUNDS,
    BlowoutModel,
    calibrate,
    factor,
)
from engine.stats.elo import EloParams, pregame_margins
from engine.stats.profile import GameLog, PlayerProfile
from engine.stats.projection import GameContext, project

SEASON = "2025-26"
D0 = date(2025, 11, 1)
BEFORE = date(2026, 6, 1)
TEAMS = [f"T{i:02d}" for i in range(12)]
STRENGTH = {t: (i - 5.5) * 3 for i, t in enumerate(TEAMS)}   # écarts réels jusqu'à ±33 pts entre extrêmes


def _schedule(days=90):
    """Six matchs par soir, scores = écart de force réel (déterministe) :
    l'Elo s'étale vite, d'où des écarts attendus d'avant-match variés."""
    games = []
    for k in range(days):
        d = D0 + timedelta(days=k)
        order = TEAMS[k % 12:] + TEAMS[:k % 12]
        rot = [order[0]] + order[1 + (k % 11):] + order[1:1 + (k % 11)]
        for j in range(6):
            home, away = rot[j], rot[11 - j]
            diff = round(STRENGTH[home] - STRENGTH[away]) or 1
            games.append({"id": f"g{k}-{j}", "date": d.isoformat(), "home_team": home, "away_team": away,
                          "game_type": "regular", "status": "final", "season": SEASON,
                          "home_score": 100 + max(diff, 0), "away_score": 100 + max(-diff, 0)})
    return games


def _synthetic(starter_slope=0.01, bench_slope=0.02, threshold=4.0, games=None):
    """Titulaire de chaque équipe (base 38 min) : minutes × (1 − a·max(0,
    |écart attendu avant-match| − t)) ; remplaçant (base 20 min) : × (1 + b·…).
    Minutes en flottants pour que l'effet soit exact (pas d'arrondi)."""
    games = games or _schedule()
    pre = pregame_margins(games, BEFORE, EloParams())
    logs = []
    for g in games:
        d = date.fromisoformat(g["date"])
        excess = max(0.0, abs(pre[g["id"]]) - threshold)
        for team, home in ((g["home_team"], True), (g["away_team"], False)):
            t = TEAMS.index(team)
            logs.append(GameLog(100 + t, g["id"], d, SEASON, team, 38 * (1 - starter_slope * excess), 40, home))
            logs.append(GameLog(200 + t, g["id"], d, SEASON, team, 20 * (1 + bench_slope * excess), 15, home))
    return games, logs, pre


def _avg_minutes(logs, pids):
    by = {}
    for l in logs:
        if l.player_id in pids:
            by.setdefault(l.player_id, []).append(l.minutes)
    return {pid: sum(m) / len(m) for pid, m in by.items()}


def test_ecarts_avant_match_varies_sous_10_pts():
    _games, _logs, pre = _synthetic()
    spread = sorted(abs(m) for m in pre.values())
    assert spread[-1] > 8 and spread[len(spread) // 2] < 10   # effet visible sous 10 pts d'écart attendu


def test_calibration_retrouve_une_pente_connue_sur_l_ecart_avant_match():
    games, logs, _pre = _synthetic()
    model = calibrate(logs, games, BEFORE)
    assert model.starter_threshold == 4.0
    assert model.bench_threshold == 4.0
    # ratio = minutes / moyenne du joueur : pente en ratio ≈ a × base / moyenne.
    s_avg = _avg_minutes(logs, {100 + i for i in range(12)})
    b_avg = _avg_minutes(logs, {200 + i for i in range(12)})
    assert model.starter_slope == pytest.approx(0.01 * 38 / (sum(s_avg.values()) / 12), rel=0.2)
    assert model.bench_slope == pytest.approx(0.02 * 20 / (sum(b_avg.values()) / 12), rel=0.2)
    assert model.starter_slope > 0.005 and model.bench_slope > 0.01
    # Appliqué à un écart attendu de 9 pts (< 10) : le facteur bouge vraiment.
    assert factor(model, 9.0, True) < 0.97
    assert factor(model, 9.0, False) > 1.05


def test_calibration_pentes_bornees():
    games, logs, _ = _synthetic(starter_slope=0.03, bench_slope=0.05)   # effets au-delà des bornes
    model = calibrate(logs, games, BEFORE)
    assert model.starter_slope == STARTER_SLOPE_BOUNDS[1]
    assert model.bench_slope == BENCH_SLOPE_BOUNDS[1]
    # Effet inverse (titulaires jouent PLUS quand l'écart attendu est grand) → borné à 0.
    games, logs, _ = _synthetic(starter_slope=-0.01, bench_slope=-0.01)
    model = calibrate(logs, games, BEFORE)
    assert model.starter_slope == 0.0
    assert model.bench_slope == 0.0


def test_calibration_sans_donnees_modele_neutre():
    assert calibrate([], [], BEFORE) == NEUTRAL
    games, logs, _ = _synthetic()
    assert calibrate(logs, games, D0) == NEUTRAL      # tous les matchs après `before`


def test_calibration_echantillon_minimum_par_groupe():
    games, logs, _ = _synthetic()
    # Remplaçants limités à 5 soirs (≈ 5 × 12 < MIN_SAMPLE matchs-joueur) : groupe neutre.
    first_days = {g["id"] for g in games if date.fromisoformat(g["date"]) < D0 + timedelta(days=5)}
    few_bench = [l for l in logs if l.player_id < 200 or l.game_id in first_days]
    assert sum(1 for l in few_bench if l.player_id >= 200) < MIN_SAMPLE
    model = calibrate(few_bench, games, BEFORE)
    assert model.bench_slope == 0.0
    assert model.starter_slope > 0


def test_calibration_ignore_les_dnp_et_les_matchs_non_termines():
    games, logs, _ = _synthetic()
    base = calibrate(logs, games, BEFORE)
    d = date.fromisoformat(games[-1]["date"])
    # DNP (0 min) : absence, pas un effet d'écart → modèle identique.
    assert calibrate(logs + [GameLog(100, games[-1]["id"], d, SEASON, "T00", 0, 0, True)], games, BEFORE) == base
    # Match reporté (non terminé) : pas d'écart d'avant-match, ses logs ne
    # comptent pas dans la pente, et il ne modifie pas l'Elo des autres.
    odd_d = d + timedelta(days=1)
    odd = {**games[0], "id": "odd", "date": odd_d.isoformat(), "status": "scheduled"}
    assert "odd" not in pregame_margins(games + [odd], BEFORE, EloParams())
    assert calibrate(logs, games + [odd], BEFORE) == base


def test_calibration_aucun_log_ni_match_du_jour_d():
    """Un match (score et logs) du soir D ne change rien à la calibration
    pour D : seuls les logs ET matchs de date < D comptent."""
    games, logs, _ = _synthetic()
    d = date.fromisoformat(games[-1]["date"]) + timedelta(days=1)
    base = calibrate(logs, games, d)
    blowout_game = {**games[0], "id": "gD", "date": d.isoformat(), "home_score": 160, "away_score": 80}
    blowout_logs = [GameLog(100, "gD", d, SEASON, "T00", 5, 5, True),
                    GameLog(200, "gD", d, SEASON, "T00", 48, 60, True)]
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
