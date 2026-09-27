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
