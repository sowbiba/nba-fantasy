from datetime import date, timedelta

from engine.rules.calendar import Night
from engine.stats.profile import GameLog, build_profile, prior_minutes, role_scales
from engine.strategy.inputs import build_decision_inputs

SEASON = "2026-27"
PRIOR = "2025-26"
TODAY = date(2026, 11, 10)


def _player(pid, team, pos="G", active=True):
    return {"id": pid, "name": f"Joueur {pid}", "team": team, "position": pos, "active": active}


def _log(pid, gid, d, team, season=SEASON, minutes=30, ttfl=40, home=True):
    return GameLog(player_id=pid, game_id=gid, date=d, season=season, team=team, minutes=minutes,
                    ttfl=ttfl, is_home=home)


def _game(gid, d, home, away, season=SEASON, game_type="regular", status="final"):
    return {"id": gid, "date": d.isoformat(), "home_team": home, "away_team": away,
            "season": season, "game_type": game_type, "status": status}


def _current_logs(pid, team, n=6, base_minutes=30, base_ttfl=40):
    return [_log(pid, f"c{pid}{i}", TODAY - timedelta(days=i + 1), team, minutes=base_minutes + i, ttfl=base_ttfl + i)
            for i in range(n)]


def _prior_logs(pid, team, n=5):
    return [_log(pid, f"p{pid}{i}", date(2026, 3, 1) + timedelta(days=i), team, season=PRIOR, minutes=28, ttfl=35)
            for i in range(n)]


def test_build_decision_inputs_matches_manual_profile_and_recent_logs():
    players = {1: _player(1, "DEN", "C"), 2: _player(2, "LAL", "G")}
    current_1, current_2 = _current_logs(1, "DEN"), _current_logs(2, "LAL")
    prior_1, prior_2 = _prior_logs(1, "DEN"), _prior_logs(2, "LAL")
    logs = current_1 + current_2 + prior_1 + prior_2

    games = [_game("c10", TODAY, "DEN", "LAL")]
    nights = [Night(date=TODAY, season=SEASON, mode="regular", n_eligible_games=1,
                    closing_at=None, is_phantom=False)]

    inputs, profiles = build_decision_inputs(
        today=TODAY, players=players, games=games, season_games=games, logs=logs,
        season=SEASON, prior=PRIOR, picks=[], second_chances=[], series_rows=[], nights=nights,
    )

    rosters = {"DEN": [1], "LAL": [2]}
    scales = role_scales(prior_minutes(prior_1 + prior_2), rosters)
    expected_1 = build_profile(1, current_1, prior_1, scales["DEN"])
    expected_2 = build_profile(2, current_2, prior_2, scales["LAL"])
    assert profiles[1] == expected_1
    assert profiles[2] == expected_2
    assert inputs.profiles == profiles

    recent_1 = inputs.recent_logs[1]
    sorted_current_1 = sorted(current_1, key=lambda l: l.date, reverse=True)[:5]
    assert recent_1 == [{"minutes": l.minutes} for l in sorted_current_1]
    assert recent_1[0]["minutes"] == sorted_current_1[0].minutes


def test_inactive_players_have_no_profile():
    players = {1: _player(1, "DEN", "C", active=True), 2: _player(2, "LAL", "G", active=False)}
    logs = _current_logs(1, "DEN") + _current_logs(2, "LAL")
    games = [_game("c10", TODAY, "DEN", "LAL")]
    nights = [Night(date=TODAY, season=SEASON, mode="regular", n_eligible_games=1,
                    closing_at=None, is_phantom=False)]

    inputs, profiles = build_decision_inputs(
        today=TODAY, players=players, games=games, season_games=games, logs=logs,
        season=SEASON, prior=PRIOR, picks=[], second_chances=[], series_rows=[], nights=nights,
    )

    assert 1 in profiles
    assert 2 not in profiles
    # recent_logs vient des logs (pas des profils) : un joueur inactif y figure
    # quand même si des logs existent (utile pour un log d'avant sa mise en repos).
    assert 2 in inputs.recent_logs


# --- Facteur « écart de force » (L3a §2) -----------------------------------

import pytest  # noqa: E402

from engine.stats.elo import EloParams  # noqa: E402


def _scored(gid, d, home, away, hs, as_):
    return {**_game(gid, d, home, away), "home_score": hs, "away_score": as_}


def _blowout_setup():
    """DEN a écrasé LAL plusieurs fois avant TODAY ; match DEN–LAL ce soir."""
    players = {1: _player(1, "DEN", "C"), 2: _player(2, "LAL", "G")}
    history = [_scored(f"h{i}", TODAY - timedelta(days=10 - i), "DEN", "LAL", 130, 95) for i in range(6)]
    logs = []
    for i, g in enumerate(history):
        d = date.fromisoformat(g["date"])
        logs.append(_log(1, g["id"], d, "DEN", minutes=36 - i, ttfl=45))
        logs.append(_log(2, g["id"], d, "LAL", minutes=30 + i, ttfl=30, home=False))
    tonight = _game("t1", TODAY, "DEN", "LAL", status="scheduled")
    nights = [Night(date=TODAY, season=SEASON, mode="regular", n_eligible_games=1,
                    closing_at=None, is_phantom=False)]
    return players, history, logs, tonight, nights


def _build(players, season_games, logs, games, nights, **kw):
    return build_decision_inputs(today=TODAY, players=players, games=games, season_games=season_games, logs=logs,
                                 season=SEASON, prior=PRIOR, picks=[], second_chances=[], series_rows=[],
                                 nights=nights, **kw)


def test_blowout_desactive_aucun_calcul_elo():
    players, history, logs, tonight, nights = _blowout_setup()
    inputs, _ = _build(players, history + [tonight], logs, [tonight], nights)
    assert inputs.expected_margins == {}
    assert inputs.blowout_model is None


def test_blowout_active_ecart_attendu_et_modele():
    players, history, logs, tonight, nights = _blowout_setup()
    inputs, _ = _build(players, history + [tonight], logs, [tonight], nights, blowout=True)
    assert inputs.expected_margins["t1"] > 70 / 28   # DEN plus fort que LAL au-delà de l'avantage du terrain
    assert inputs.blowout_model is not None


def test_blowout_un_resultat_du_soir_d_ne_change_pas_la_projection_de_d():
    """Pas de fuite : le score final (et les logs) du match du soir D ne
    changent ni l'écart attendu, ni le modèle ; le score seul ne change pas
    les projections de D (les logs de D ne sont jamais passés au moteur :
    `logs_before` en backtest, inexistants avant le match en prod)."""
    from engine.strategy.regular import decide
    players, history, logs, tonight, nights = _blowout_setup()
    a, _ = _build(players, history + [tonight], logs, [tonight], nights, blowout=True)
    played = {**tonight, "status": "final", "home_score": 80, "away_score": 140}   # LAL gagne de 60
    d_logs = [_log(1, "t1", TODAY, "DEN", minutes=12, ttfl=5), _log(2, "t1", TODAY, "LAL", minutes=44, ttfl=70)]
    b, _ = _build(players, history + [played], logs + d_logs, [played], nights, blowout=True)
    assert a.expected_margins == b.expected_margins
    assert a.blowout_model == b.blowout_model
    c, _ = _build(players, history + [played], logs, [played], nights, blowout=True)
    # Modèle fixe non neutre (les données synthétiques n'ont qu'un seul écart
    # final, donc un modèle calibré neutre) : le facteur agit vraiment.
    from engine.stats.blowout import BlowoutModel
    model = BlowoutModel(0.02, 0.0, 0.03, 0.0)
    da, dc = decide(a, blowout=model), decide(c, blowout=model)
    assert da.recommendations and da.recommendations[0].cell.ctx.expected_margin is not None
    assert da.recommendations[0].cell.projection != decide(a).recommendations[0].cell.projection
    assert [(r.cell.player_id, r.cell.projection) for r in da.recommendations] == \
           [(r.cell.player_id, r.cell.projection) for r in dc.recommendations]


def test_blowout_correction_blessures_seulement_ce_soir_et_si_calibree():
    players, history, logs, tonight, nights = _blowout_setup()
    later = _game("t2", TODAY + timedelta(days=3), "DEN", "LAL", status="scheduled")
    hurt = {**players, 1: {**players[1], "injury_status": "Out"}}
    games = [tonight, later]
    raw, _ = _build(players, history + games, logs, games, nights, blowout=True,
                    elo_params=EloParams(elo_per_share=300))
    no_eps, _ = _build(hurt, history + games, logs, games, nights, blowout=True)   # elo_per_share = 0
    corrected, _ = _build(hurt, history + games, logs, games, nights, blowout=True,
                          elo_params=EloParams(elo_per_share=300))
    assert no_eps.expected_margins == raw.expected_margins
    # Le joueur 1 porte toute la production de DEN : note −300 ce soir seulement.
    assert corrected.expected_margins["t1"] == pytest.approx(raw.expected_margins["t1"] - 300 / 28)
    assert corrected.expected_margins["t2"] == raw.expected_margins["t2"]
