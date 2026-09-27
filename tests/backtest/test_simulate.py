"""Simulation soir par soir sur de petites saisons synthétiques (sans DB)."""
from datetime import date, timedelta

import pytest

import engine.backtest.simulate as sim
from engine.backtest.data import SeasonData
from engine.backtest.simulate import BacktestResult, NightResult, simulate, user_result
from engine.rules.availability import COOLDOWN_DAYS, PickRow
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


def test_seed_picks_amorce_le_cooldown_avant_le_debut_de_la_fenetre():
    # Un vrai pick posé 10 jours avant le début de la fenêtre bloque son
    # joueur jusqu'à J+30 (R3, dans les deux sens comme `is_available`) :
    # le joueur 1 (le meilleur, normalement pické soir 1) doit être exclu de
    # toute la fenêtre (6 soirées, largement < 30 jours après le seed).
    data = _season(SIX_NIGHTS)
    seed_date = SIX_NIGHTS[0] - timedelta(days=10)
    seed = [PickRow(id=999, player_id=1, date=seed_date, mode="regular", season=SEASON, is_x2=False)]

    seeded = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available", seed_picks=seed)
    assert all(n.player_id != 1 for n in seeded.nights)
    assert seeded.nights[0].player_id == 2   # le meilleur restant, disponible

    # Sans seed, le joueur 1 est bien pické soir 1 (comportement existant).
    naive = simulate(data, SIX_NIGHTS[0], SIX_NIGHTS[-1], "best_available")
    assert naive.nights[0].player_id == 1

    # Le pick d'amorçage n'apparaît jamais dans les résultats (pas de soirée
    # au 10 novembre, pas de points pour le joueur 1 ce jour-là).
    assert all(n.night in SIX_NIGHTS for n in seeded.nights)
    assert seed_date not in {n.night for n in seeded.nights}


def test_seed_picks_x2_du_mois_deja_pose_empeche_un_second_x2():
    # x2 réel posé début novembre (avant la fenêtre) : le mois est déjà
    # servi, ni best_available (référence naïve) ni plan ne doivent poser un
    # second x2 en novembre à l'intérieur de la fenêtre.
    nights = [date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights)
    seed = [PickRow(id=998, player_id=4, date=date(2026, 11, 5), mode="regular", season=SEASON, is_x2=True)]

    naive = simulate(data, nights[0], nights[-1], "best_available", seed_picks=seed)
    assert not any(n.is_x2 for n in naive.nights if n.night.month == 11)
    assert any(n.is_x2 for n in naive.nights if n.night.month == 12)   # décembre : mois neuf, pas amorcé

    plan = simulate(data, nights[0], nights[-1], "plan", seed_picks=seed)
    assert not any(n.is_x2 for n in plan.nights if n.night.month == 11)

    # Sans le seed, novembre pose bien son propre x2 (comportement existant).
    without_seed = simulate(data, nights[0], nights[-1], "best_available")
    assert any(n.is_x2 for n in without_seed.nights if n.night.month == 11)


# --- I-3 : best_available_x2plan (comportement livré) ---------------------------

def test_x2plan_garde_les_picks_du_meilleur_dispo_et_pose_un_x2_par_mois():
    nights = [date(2026, 11, 28), date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights)
    ba = simulate(data, nights[0], nights[-1], "best_available")
    x2plan = simulate(data, nights[0], nights[-1], "best_available_x2plan")
    # Mêmes picks (rang 1 best-available chaque soir) : seul le x2 change.
    assert [n.player_id for n in x2plan.nights] == [n.player_id for n in ba.nights]
    november = [n for n in x2plan.nights if n.night.month == 11 and n.is_x2]
    assert len(november) == 1   # fin de novembre visible : x2 forcé, posé sur un pick
    assert november[0].points == 2 * BASE[november[0].player_id]


def test_x2plan_replanifie_avec_le_pick_du_soir_fixe_et_suit_plan_du_soir(monkeypatch):
    nights = [date(2026, 11, 28), date(2026, 11, 29), date(2026, 11, 30), date(2026, 12, 1)]
    data = _season(nights)
    calls = []
    real_decide = sim.decide

    def spy(inputs, **kwargs):
        decision = real_decide(inputs, **kwargs)
        calls.append((inputs, kwargs, decision))
        return decision

    monkeypatch.setattr(sim, "decide", spy)
    result = simulate(data, nights[0], nights[-1], "best_available_x2plan")
    # Deux décisions par soirée avec reco : la reco, puis le plan avec le pick fixé.
    assert len(calls) == 2 * len(result.nights)
    for i, night in enumerate(result.nights):
        first, second = calls[2 * i], calls[2 * i + 1]
        assert first[1]["tonight_source"] == second[1]["tonight_source"] == "best_available"
        fixed = [p for p in second[0].picks if p.date == night.night]
        assert [p.player_id for p in fixed] == [night.player_id]
        entry = second[2].plan.get(night.night)
        expected = entry is not None and entry.cell.player_id == night.player_id and entry.is_x2
        # Un seul x2 par mois : un x2 suggéré après celui du mois n'est pas posé.
        assert night.is_x2 == (expected and not any(
            n.is_x2 for n in result.nights[:i] if n.night.month == night.night.month))
