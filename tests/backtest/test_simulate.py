"""Simulation soir par soir sur de petites saisons synthétiques (sans DB)."""
from datetime import date, timedelta

import pytest

import engine.backtest.simulate as sim
from engine.backtest.data import SeasonData
from engine.backtest.simulate import BacktestResult, NightResult, simulate, user_result
from engine.rules.availability import COOLDOWN_DAYS
from engine.stats.profile import GameLog

SEASON = "2026-27"
PRIOR = "2025-26"
HOME, AWAY = "AAA", "BBB"
# Joueurs 1, 2 chez AAA ; 3, 4 chez BBB. Moyenne passée : 1 > 2 > 3 > 4.
TEAMS = {1: HOME, 2: HOME, 3: AWAY, 4: AWAY}
BASE = {1: 50, 2: 40, 3: 30, 4: 20}
SIX_NIGHTS = [date(2026, 11, 20) + timedelta(days=i) for i in range(6)]


def _log(pid, d, minutes, ttfl, season=SEASON):
    return GameLog(player_id=pid, game_id=f"g_{d.isoformat()}", date=d, season=season,
                   team=TEAMS[pid], minutes=minutes, ttfl=ttfl, is_home=TEAMS[pid] == HOME)


def _season(nights, overrides=None, picks=None):
    """Un match AAA–BBB par soirée ; chaque joueur joue 30 min à son score de
    base, sauf `overrides[(pid, d)]` = (minutes, ttfl) ou None (pas de log)."""
    overrides = overrides or {}
    games = [{"id": f"g_{d.isoformat()}", "date": d.isoformat(), "home_team": HOME, "away_team": AWAY,
              "game_type": "regular", "status": "final", "tip_off": None, "season": SEASON} for d in nights]
    logs = []
    for pid, base in BASE.items():
        for i in range(10):   # saison précédente : prior des profils (30 min joués)
            logs.append(_log(pid, date(2026, 3, 1) + timedelta(days=i), 30, base, season=PRIOR))
        for d in nights:
            o = overrides.get((pid, d), (30, base))
            if o is not None:
                logs.append(_log(pid, d, *o))
    players = {pid: {"id": pid, "name": f"P{pid}", "position": "F"} for pid in BASE}
    return SeasonData(season=SEASON, prior=PRIOR, players=players, games=games, logs=logs,
                      picks=picks or [], second_chances=[])


def _by_night(result):
    return {n.night: n for n in result.nights}


def test_pas_de_fuite_le_log_du_soir_n_est_jamais_dans_les_entrees(monkeypatch):
    seen = []
    real = sim.build_decision_inputs

    def spy(**kw):
        assert all(l.date < kw["today"] for l in kw["logs"])
        seen.append(kw["today"])
        return real(**kw)

    monkeypatch.setattr(sim, "build_decision_inputs", spy)
    # Le joueur 4 (le plus faible) explose le soir 1 : invisible avant, il
    # n'est pas choisi ce soir-là.
    data = _season(SIX_NIGHTS, {(4, SIX_NIGHTS[0]): (30, 500)})
    result = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available")
    assert seen == SIX_NIGHTS
    assert result.nights[0].player_id == 1


def test_cooldown_un_joueur_n_est_pas_rechoisi_avant_j_plus_30():
    nights = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6),
              date(2026, 12, 1), date(2026, 12, 2)]
    data = _season(nights)
    result = simulate(data, nights[0], nights[-1], "best_available")
    picks = [(n.night, n.player_id) for n in result.nights if n.player_id is not None]
    for i, (d1, p1) in enumerate(picks):
        for d2, p2 in picks[i + 1:]:
            if p1 == p2:
                assert (d2 - d1).days >= COOLDOWN_DAYS
    by = _by_night(result)
    assert [by[d].player_id for d in nights[:4]] == [1, 2, 3, 4]
    assert by[date(2026, 11, 6)].player_id is None           # tout le monde est bloqué
    assert by[date(2026, 12, 1)].player_id is None           # J+29 : joueur 1 encore bloqué
    assert by[date(2026, 12, 2)].player_id == 1              # J+30 : de nouveau disponible


def test_dnp_zero_point_compte_dans_zeros_et_consomme_le_cooldown():
    data = _season(SIX_NIGHTS, {(1, SIX_NIGHTS[0]): None})
    result = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available")
    first = result.nights[0]
    assert first.player_id == 1 and first.points == 0
    assert all(n.player_id != 1 for n in result.nights[1:])
    # soir 1 (DNP) + soirs 5 et 6 (plus de candidat)
    assert result.zeros == 3


def test_x2_sur_score_negatif_double_le_negatif():
    # 30/11 = dernière soirée de novembre : x2 naïf posé sur le pick du soir (joueur 2).
    nights = [date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights, {(2, date(2026, 11, 30)): (30, -5)})
    result = simulate(data, nights[0], nights[-1], "best_available")
    by = _by_night(result)
    last = by[date(2026, 11, 30)]
    assert last.player_id == 2 and last.is_x2 and last.points == -10
    assert not by[date(2026, 11, 29)].is_x2
    # 01/12 est aussi la dernière soirée (connue) de décembre : x2 du mois.
    assert by[date(2026, 12, 1)].is_x2
    assert result.x2_gain == -5 + BASE[by[date(2026, 12, 1)].player_id]


def test_x2_sur_dnp_vaut_zero():
    nights = [date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights, {(2, date(2026, 11, 30)): None})
    result = simulate(data, nights[0], nights[-1], "best_available")
    last = _by_night(result)[date(2026, 11, 30)]
    assert last.player_id == 2 and last.is_x2 and last.points == 0
    assert sum(n.points // 2 for n in result.nights if n.is_x2 and n.night.month == 11) == 0


def test_plan_pose_un_seul_x2_dans_le_mois_et_le_double():
    nights = [date(2026, 11, 28), date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights)
    result = simulate(data, nights[0], nights[-1], "plan")
    november = [n for n in result.nights if n.night.month == 11]
    doubled = [n for n in november if n.is_x2]
    assert len(doubled) == 1
    assert doubled[0].points == 2 * BASE[doubled[0].player_id]
    december = [n for n in result.nights if n.night.month == 12 and n.is_x2]
    assert result.x2_gain == BASE[doubled[0].player_id] + sum(BASE[n.player_id] for n in december)


def test_average_compte_chaque_soiree_eligible_y_compris_sans_candidat():
    data = _season(SIX_NIGHTS)
    result = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available")
    assert len(result.nights) == 6
    assert [n.player_id for n in result.nights] == [1, 2, 3, 4, None, None]
    assert result.average == pytest.approx(sum(BASE.values()) / 6)


def test_average_zero_sans_soiree():
    assert BacktestResult("user", "none", []).average == 0.0


def test_user_result_reproduit_les_vrais_picks_x2_compris():
    nights = SIX_NIGHTS
    data = _season(nights, {(3, nights[1]): (30, -4), (4, nights[2]): None}, picks=[
        {"id": 1, "player_id": 1, "date": nights[0].isoformat(), "mode": "regular", "is_x2": False},
        {"id": 2, "player_id": 3, "date": nights[1].isoformat(), "mode": "regular", "is_x2": True},
        {"id": 3, "player_id": 4, "date": nights[2].isoformat(), "mode": "regular", "is_x2": False},
        {"id": 4, "player_id": 2, "date": nights[3].isoformat(), "mode": "regular", "is_x2": True},
    ])
    result = user_result(data, nights[0], nights[-1])
    assert result.strategy == "user"
    assert result.nights == [
        NightResult(nights[0], 1, False, 50),
        NightResult(nights[1], 3, True, -8),
        NightResult(nights[2], 4, False, 0),
        NightResult(nights[3], 2, True, 80),
        NightResult(nights[4], None, False, 0),
        NightResult(nights[5], None, False, 0),
    ]
    assert result.average == pytest.approx((50 - 8 + 0 + 80) / 6)
    assert result.x2_gain == -4 + 40


def test_dnp_oracle_ne_choisit_jamais_un_joueur_absent_le_soir_meme():
    data = _season(SIX_NIGHTS, {(1, SIX_NIGHTS[0]): None, (2, SIX_NIGHTS[1]): (0, 0)})
    oracle = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available", injury_mode="dnp_oracle")
    for n in oracle.nights:
        if n.player_id is not None:
            assert sim.played_on(data, n.player_id, n.night)
    assert oracle.nights[0].player_id not in (None, 1)
    assert all(n.points > 0 for n in oracle.nights if n.player_id is not None)
    # Sans oracle (personne n'est blessé), le joueur 1 est choisi et fait 0.
    naive = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available")
    assert naive.nights[0].player_id == 1 and naive.nights[0].points == 0


def test_strategie_ou_mode_inconnu():
    data = _season(SIX_NIGHTS)
    with pytest.raises(ValueError):
        simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "user")
    with pytest.raises(ValueError):
        simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available", injury_mode="oracle")
