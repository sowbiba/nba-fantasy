from datetime import date, timedelta

from engine.jobs.local_nightly import run
from tests.jobs.fakes import FakeRepo, FakeStatsSource

TODAY = date(2026, 11, 2)
TEAMS = [{"id": 1, "abbreviation": "DEN"}, {"id": 2, "abbreviation": "LAL"}]


def _roster(pid, team):
    return {"id": pid, "name": f"J{pid}", "team": team, "position": "G", "active": True}


def test_effectifs_et_desactivation_des_joueurs_coupes():
    repo = FakeRepo(players=[{"id": 9, "name": "Coupé", "team": "DEN", "position": "F", "active": True}])
    nba = FakeStatsSource(rosters={"DEN": [_roster(1, "DEN")], "LAL": [_roster(2, "LAL")]})
    run(repo, nba, TODAY, TEAMS)
    assert repo.players[1]["team"] == "DEN" and repo.players[2]["active"] is True
    assert repo.players[9]["active"] is False


def test_pas_de_desactivation_si_un_effectif_manque():
    repo = FakeRepo(players=[{"id": 9, "name": "Coupé", "team": "DEN", "position": "F", "active": True}])
    nba = FakeStatsSource(rosters={"DEN": [_roster(1, "DEN")]}, fail_teams={"LAL"})
    warnings = run(repo, nba, TODAY, TEAMS)
    assert repo.players[9]["active"] is True
    assert any("LAL" in w for w in warnings)


def test_historique_saison_courante_depuis_j_moins_3():
    game = {"0022600010": {"id": "0022600010", "date": "2026-10-31", "home_team": "DEN",
                           "away_team": "LAL", "status": "final"}}
    logs = [{"player_id": 5, "game_id": "0022600010", "date": "2026-10-31", "team": "DEN", "minutes": 30,
             "ttfl_score": 40, "is_home": True, "pts": 20, "reb": 5, "ast": 5, "stl": 1, "blk": 1,
             "fgm": 8, "fga": 15, "tpm": 2, "tpa": 5, "ftm": 2, "fta": 2, "tov": 1, "fouls": 2}]
    players = {5: {"id": 5, "name": "Nouveau", "team": "DEN"}}
    nba = FakeStatsSource(game_logs={("2026-27", "Regular Season"): (game, logs, players)})
    repo = FakeRepo()
    run(repo, nba, TODAY, [])
    assert nba.log_calls == [("2026-27", "Regular Season", TODAY - timedelta(days=3))]
    assert repo.players[5]["active"] is False and repo.players[5]["position"] == "F"
    assert (5, "0022600010") in repo.logs


def test_backfill_saison_complete_regular_et_playoffs():
    nba = FakeStatsSource()
    run(FakeRepo(), nba, TODAY, [], backfill_season="2025-26")
    assert nba.log_calls == [("2025-26", "Regular Season", None), ("2025-26", "Playoffs", None)]


def test_matchups_bruts_des_matchs_eligibles_termines():
    games = [{"id": "0022600010", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "DEN",
              "away_team": "LAL", "status": "final", "game_type": "regular", "season": "2026-27", "series_id": None},
             {"id": "0012600001", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "DEN",
              "away_team": "LAL", "status": "final", "game_type": "preseason", "season": "2026-27", "series_id": None}]
    row = {"game_id": "0022600010", "off_team": "DEN", "off_player_id": 1, "off_player_name": "A",
           "def_player_id": 2, "def_player_name": "B", "matchup_seconds": 300.0, "partial_possessions": 10.0,
           "player_points": 8, "matchup_assists": 1, "matchup_turnovers": 0, "matchup_blocks": 0,
           "matchup_fgm": 3, "matchup_fga": 6, "matchup_tpm": 1, "matchup_tpa": 2, "matchup_ftm": 1, "matchup_fta": 1}
    repo = FakeRepo(games=games)
    run(repo, FakeStatsSource(matchups={"0022600010": [row], "0012600001": [row]}), TODAY, [])
    assert [(m["game_id"], m["def_team"]) for m in repo.matchups] == [("0022600010", "LAL")]
