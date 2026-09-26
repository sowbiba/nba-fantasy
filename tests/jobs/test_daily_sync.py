from datetime import UTC, date, datetime, timedelta

from engine.jobs.daily_sync import run
from tests.jobs.fakes import FakeNbaSource, FakeRepo

TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def _player(pid, team, pos="G", **k):
    return {"id": pid, "name": f"Joueur {pid}", "team": team, "position": pos,
            "injury_status": None, "active": True, **k}


def _log(pid, gid, d, team, minutes=34, ttfl=50, season="2026-27", home=True):
    return {"player_id": pid, "game_id": gid, "date": d.isoformat(), "season": season, "team": team,
            "minutes": minutes, "ttfl_score": ttfl, "is_home": home}


def _base_repo(**over):
    players = [_player(1, "DEN", "C"), _player(2, "LAL"), _player(3, "BOS")]
    past = TODAY - timedelta(days=2)
    games = [
        {"id": "0022600010", "date": past.isoformat(), "home_team": "DEN", "away_team": "LAL",
         "status": "final", "game_type": "regular", "season": "2026-27"},
        {"id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "BOS",
         "away_team": "DEN", "status": "final", "game_type": "regular", "season": "2026-27"},
    ]
    logs = [_log(1, "0022600010", past, "DEN"), _log(2, "0022600010", past, "LAL", ttfl=35, home=False)]
    # Saison précédente : sans prior, un seul match courant laisse le profil
    # proche du rookie (< 15 min attendues) et personne ne serait candidat.
    for pid, team in ((1, "DEN"), (2, "LAL"), (3, "BOS")):
        logs += [_log(pid, f"prior{pid}{i}", date(2026, 3, 1) + timedelta(days=i), team, season="2025-26")
                 for i in range(5)]
    picks = [{"id": 1, "player_id": 3, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": False}]
    kwargs = dict(players=players, games=games, logs=logs, picks=picks)
    kwargs.update(over)
    return FakeRepo(**kwargs)


SCHEDULE = [
    {"id": "0022600020", "date": TODAY.isoformat(), "home_team": "DEN", "away_team": "LAL",
     "tip_off": "2026-11-03T01:00:00Z"},
    {"id": "0012600099", "date": (TODAY + timedelta(days=1)).isoformat(), "home_team": "BOS",
     "away_team": "LAL", "tip_off": None},
    {"id": "0022600021", "date": (TODAY + timedelta(days=5)).isoformat(), "home_team": "BOS",
     "away_team": "DEN", "tip_off": None},
]

BOX = {"0022600011": [
    {"player_id": 3, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "team": "BOS",
     "minutes": 36, "ttfl_score": 44, "is_home": True, "pts": 30, "reb": 5, "ast": 5, "stl": 1, "blk": 0,
     "fgm": 10, "fga": 20, "tpm": 3, "tpa": 8, "ftm": 7, "fta": 8, "tov": 2, "fouls": 2},
    {"player_id": 999, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "team": "BOS",
     "minutes": 5, "ttfl_score": 2, "is_home": True, "pts": 2, "reb": 0, "ast": 0, "stl": 0, "blk": 0,
     "fgm": 1, "fga": 1, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "tov": 0, "fouls": 0},
]}


def test_daily_sync_de_bout_en_bout():
    repo = _base_repo()
    result = run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: {}, TODAY, NOW)
    # soirées : ce soir et J+5 ; la présaison de J+1 n'est pas une soirée
    assert [n["date"] for n in repo.nights] == [TODAY.isoformat(), (TODAY + timedelta(days=5)).isoformat()]
    # box score ingéré et pick scoré
    assert repo.picks[0]["actual_score"] == 44
    # recos du soir écrites, avec les colonnes S1
    recs = repo.recommendations[TODAY]
    assert result.recommendations == len(recs) > 0
    assert {"projection", "p_play", "value", "lock_value", "locked_until", "best_future",
            "estimated_score", "rank", "tier", "pros", "cons", "verdict", "tags"} <= set(recs[0])
    assert recs[0]["rank"] == 1
    assert repo.plan and all(r["generated_at"] == NOW.isoformat() for r in repo.plan)


def test_daily_sync_ignore_logs_de_joueurs_inconnus():
    repo = _base_repo()
    result = run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: {}, TODAY, NOW)
    assert (999, "0022600011") not in repo.logs
    assert any("inconnu" in w for w in result.warnings)


def test_daily_sync_continue_si_nba_indisponible():
    repo = _base_repo()
    repo.upsert_games(SCHEDULE)          # calendrier déjà en base
    result = run(repo, FakeNbaSource(fail=True), lambda: {}, TODAY, NOW)
    assert result.warnings                # étapes réseau notées, pas d'exception
    assert repo.recommendations[TODAY]   # la décision tourne sur les données en base


def test_daily_sync_blessures():
    repo = _base_repo()
    injuries = {"LAL": [{"name": "Joueur 2", "status": "Out", "detail": "Genou", "return_date": None,
                         "short_comment": "", "updated_at": ""}]}
    run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: injuries, TODAY, NOW)
    assert repo.players[2]["injury_status"] == "Out"
    assert 2 not in [r["player_id"] for r in repo.recommendations[TODAY]]
