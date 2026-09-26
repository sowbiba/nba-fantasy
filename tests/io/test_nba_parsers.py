from datetime import date

import pytest

from engine.io.guard import ApiGuard
from engine.io.nba import (
    NbaSource, parse_league_game_log, parse_live_box_score, parse_matchups,
    parse_roster, parse_schedule, parse_scoreboard,
)

SCHEDULE = {"leagueSchedule": {"gameDates": [
    {"gameDate": "10/20/2026 00:00:00", "games": [
        {"gameId": "0022600001", "gameDateTimeUTC": "2026-10-20T23:30:00Z",
         "homeTeam": {"teamTricode": "BOS"}, "awayTeam": {"teamTricode": "NYK"}},
    ]},
    {"gameDate": "12/31/2026 00:00:00", "games": [
        {"gameId": "0022600500", "homeTeam": {"teamTricode": "LAL"}, "awayTeam": {}},
    ]},
]}}


def test_parse_schedule_fenetre_et_sans_statut():
    rows = parse_schedule(SCHEDULE, date(2026, 10, 1), date(2026, 11, 30))
    assert rows == [{"id": "0022600001", "date": "2026-10-20", "home_team": "BOS",
                     "away_team": "NYK", "tip_off": "2026-10-20T23:30:00Z"}]


def test_parse_schedule_equipe_inconnue_devient_tbd():
    rows = parse_schedule(SCHEDULE, date(2026, 12, 1), date(2027, 1, 31))
    assert rows[0]["away_team"] == "TBD"


def test_parse_scoreboard_statuts_et_date_du_scoreboard():
    sb = {"gameDate": "2026-10-20", "games": [
        {"gameId": "0022600001", "gameStatus": 3, "gameTimeUTC": "2026-10-20T23:30:00Z",
         "homeTeam": {"teamTricode": "BOS", "score": 110}, "awayTeam": {"teamTricode": "NYK", "score": 104}},
        {"gameId": "0022600002", "gameStatus": 1, "gameTimeUTC": None,
         "homeTeam": {"teamTricode": "LAL", "score": 0}, "awayTeam": {"teamTricode": "GSW", "score": 0}},
    ]}
    rows = parse_scoreboard(sb, date(2026, 10, 21))
    assert rows[0] == {"id": "0022600001", "date": "2026-10-20", "home_team": "BOS", "away_team": "NYK",
                       "tip_off": "2026-10-20T23:30:00Z", "status": "final",
                       "home_score": 110, "away_score": 104}
    assert rows[1]["status"] == "scheduled" and rows[1]["home_score"] is None


def _player(pid, minutes, **stats):
    base = {"points": 0, "reboundsTotal": 0, "assists": 0, "steals": 0, "blocks": 0,
            "fieldGoalsMade": 0, "fieldGoalsAttempted": 0, "threePointersMade": 0,
            "threePointersAttempted": 0, "freeThrowsMade": 0, "freeThrowsAttempted": 0,
            "turnovers": 0, "foulsPersonal": 0, "minutes": minutes}
    base.update(stats)
    return {"personId": pid, "firstName": "A", "familyName": "B", "statistics": base}


def test_parse_live_box_score_date_us_equipe_et_dnp():
    game = {"gameId": "0022600001",
            "homeTeam": {"teamTricode": "BOS", "players": [
                _player(1, "PT34M12.00S", points=28, reboundsTotal=10, assists=6, steals=2, blocks=1,
                        fieldGoalsMade=11, fieldGoalsAttempted=20, threePointersMade=3,
                        threePointersAttempted=7, freeThrowsMade=3, freeThrowsAttempted=4, turnovers=4)]},
            "awayTeam": {"teamTricode": "NYK", "players": [_player(2, "PT00M00.00S")]}}
    rows = parse_live_box_score(game, "2026-10-20")
    star = next(r for r in rows if r["player_id"] == 1)
    assert (star["date"], star["team"], star["minutes"], star["ttfl_score"], star["is_home"]) == (
        "2026-10-20", "BOS", 34, 46, True)
    dnp = next(r for r in rows if r["player_id"] == 2)
    assert (dnp["minutes"], dnp["ttfl_score"], dnp["is_home"], dnp["team"]) == (0, 0, False, "NYK")


LGL = [
    {"PLAYER_ID": 1, "PLAYER_NAME": "Jokic", "TEAM_ABBREVIATION": "DEN", "GAME_ID": "0022500010",
     "GAME_DATE": "2025-10-22", "MATCHUP": "DEN vs. GSW", "MIN": 35, "PTS": 30, "REB": 12, "AST": 10,
     "STL": 1, "BLK": 1, "FGM": 12, "FGA": 20, "FG3M": 2, "FG3A": 5, "FTM": 4, "FTA": 5, "TOV": 3, "PF": 2},
    {"PLAYER_ID": 2, "PLAYER_NAME": "Curry", "TEAM_ABBREVIATION": "GSW", "GAME_ID": "0022500010",
     "GAME_DATE": "2025-10-22", "MATCHUP": "GSW @ DEN", "MIN": "31:30", "PTS": 25, "REB": 4, "AST": 6,
     "STL": 1, "BLK": 0, "FGM": 9, "FGA": 19, "FG3M": 5, "FG3A": 12, "FTM": 2, "FTA": 2, "TOV": 2, "PF": 1},
]


def test_parse_league_game_log():
    games, logs, players = parse_league_game_log(LGL)
    assert games == {"0022500010": {"id": "0022500010", "date": "2025-10-22", "home_team": "DEN",
                                    "away_team": "GSW", "status": "final"}}
    jokic = next(l for l in logs if l["player_id"] == 1)
    assert (jokic["team"], jokic["is_home"], jokic["minutes"], jokic["fouls"]) == ("DEN", True, 35, 2)
    assert jokic["ttfl_score"] == 30 + 12 + 10 + 1 + 1 + 12 + 2 + 4 - 3 - 8 - 3 - 1
    curry = next(l for l in logs if l["player_id"] == 2)
    assert (curry["is_home"], curry["minutes"]) == (False, 31)
    assert players[2] == {"id": 2, "name": "Curry", "team": "GSW"}


def test_parse_league_game_log_format_date_texte():
    rows = [dict(LGL[0], GAME_DATE="OCT 22, 2025")]
    games, logs, _ = parse_league_game_log(rows)
    assert logs[0]["date"] == "2025-10-22"


def test_parse_roster_postes():
    rows = [{"PLAYER_ID": 1, "PLAYER": "A", "POSITION": "G-F"},
            {"PLAYER_ID": 2, "PLAYER": "B", "POSITION": "Center"},
            {"PLAYER_ID": 3, "PLAYER": "C", "POSITION": ""}]
    assert [(r["id"], r["position"], r["team"], r["active"]) for r in parse_roster(rows, "DEN")] == [
        (1, "G", "DEN", True), (2, "C", "DEN", True), (3, "F", "DEN", True)]


def test_parse_matchups():
    rec = {"gameId": "0022600001", "teamTricode": "BOS", "personIdOff": 1, "firstNameOff": "A",
           "familyNameOff": "B", "personIdDef": 2, "firstNameDef": "C", "familyNameDef": "D",
           "matchupMinutesSort": 300.0, "partialPossessions": 20.5, "playerPoints": 8,
           "matchupAssists": 1, "matchupTurnovers": 0, "matchupBlocks": 0,
           "matchupFieldGoalsMade": 3, "matchupFieldGoalsAttempted": 6,
           "matchupThreePointersMade": 1, "matchupThreePointersAttempted": 2,
           "matchupFreeThrowsMade": 1, "matchupFreeThrowsAttempted": 1}
    [row] = parse_matchups([rec], "0022600001")
    assert (row["off_player_id"], row["def_player_id"], row["matchup_seconds"], row["player_points"]) == (1, 2, 300.0, 8)


def test_stats_nba_interdit_depuis_github():
    src = NbaSource(ApiGuard(), allow_stats=False)
    with pytest.raises(RuntimeError, match="stats.nba.com"):
        src.league_game_log("2026-27", "Regular Season")
