# sync/fetcher.py
"""Fetch NBA data from cdn.nba.com and nba_api.

Collects: today's games, box scores, player game logs,
team rosters, team defense stats, playoff series.
"""
import time
from datetime import date, datetime, timedelta

from nba_api.stats.endpoints import (
    LeagueDashTeamStats,
    CommonTeamRoster,
    PlayerGameLog,
    ScoreboardV3,
)
from nba_api.live.nba.endpoints import BoxScore, ScoreBoard

from sync.config import NBA_API_DELAY
from sync.ttfl import compute_ttfl_score

import numpy as np


def fetch_today_scoreboard() -> dict:
    """Fetch today's scoreboard from nba_api live endpoint."""
    board = ScoreBoard()
    data = board.get_dict()
    return data["scoreboard"]


def parse_today_games(scoreboard: dict, today: date) -> list[dict]:
    """Parse scoreboard into game dicts for the games table.

    Uses the scoreboard's own `gameDate` field when present — the NBA live
    scoreboard sometimes keeps the previous game day active well into the
    morning (ET). Trusting `today` unconditionally would mis-date yesterday's
    late play-in games as today's.
    """
    sb_date_str = scoreboard.get("gameDate")
    sb_date = today
    if sb_date_str:
        try:
            sb_date = datetime.strptime(sb_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            sb_date = today
    games = []
    for game in scoreboard.get("games", []):
        game_id = game["gameId"]
        home = game["homeTeam"]["teamTricode"]
        away = game["awayTeam"]["teamTricode"]
        tip_off_utc = game.get("gameTimeUTC")

        if game["gameStatus"] == 3:
            status = "final"
        elif game["gameStatus"] == 2:
            status = "live"
        else:
            status = "scheduled"

        home_score = game["homeTeam"].get("score", 0) or 0
        away_score = game["awayTeam"].get("score", 0) or 0

        games.append({
            "id": game_id,
            "date": sb_date.isoformat(),
            "home_team": home,
            "away_team": away,
            "tip_off": tip_off_utc,
            "status": status,
            "home_score": home_score if status != "scheduled" else None,
            "away_score": away_score if status != "scheduled" else None,
        })
    return games


def fetch_live_box_score(game_id: str) -> list[dict]:
    """Fetch box score for a finished/live game. Returns player stat dicts."""
    try:
        box = BoxScore(game_id=game_id)
        data = box.get_dict()["game"]
    except Exception:
        return []

    players = []
    game_date = data.get("gameTimeUTC", "")[:10]

    for side in ["homeTeam", "awayTeam"]:
        team = data[side]
        team_tricode = team["teamTricode"]
        is_home = side == "homeTeam"

        for p in team.get("players", []):
            stats = p.get("statistics", {})
            # DNP / did-not-dress players still appear in the box score with
            # minutes == "PT00M". We log them as a 0-TTFL, 0-minute row so
            # that rotation-fringe players see their aggregates pulled down
            # by the nights they didn't play — previously we skipped these
            # rows and the averages were computed only on games actually
            # played, which made bench players look like everyday rotation.

            # Parse minutes from ISO duration "PT32M12.00S"
            min_str = (stats.get("minutes") if stats else None) or "PT0M"
            minutes = 0
            if "M" in min_str:
                try:
                    minutes = int(min_str.split("T")[1].split("M")[0])
                except (IndexError, ValueError):
                    pass

            pts = (stats or {}).get("points", 0)
            reb = (stats or {}).get("reboundsTotal", 0)
            ast = (stats or {}).get("assists", 0)
            stl = (stats or {}).get("steals", 0)
            blk = (stats or {}).get("blocks", 0)
            fgm = (stats or {}).get("fieldGoalsMade", 0)
            fga = (stats or {}).get("fieldGoalsAttempted", 0)
            tpm = (stats or {}).get("threePointersMade", 0)
            tpa = (stats or {}).get("threePointersAttempted", 0)
            ftm = (stats or {}).get("freeThrowsMade", 0)
            fta = (stats or {}).get("freeThrowsAttempted", 0)
            tov = (stats or {}).get("turnovers", 0)

            ttfl = compute_ttfl_score(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov)

            players.append({
                "player_id": p["personId"],
                "player_name": f"{p['firstName']} {p['familyName']}",
                "team": team_tricode,
                "game_id": data["gameId"],
                "date": game_date,
                "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
                "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa,
                "ftm": ftm, "fta": fta, "tov": tov,
                "minutes": minutes,
                "ttfl_score": ttfl,
                "is_home": is_home,
            })

    return players


def fetch_player_game_logs_nba_api(player_id: int, season: str = "2025-26") -> list[dict]:
    """Fetch game logs for a player via nba_api stats endpoint."""
    time.sleep(NBA_API_DELAY)
    try:
        log = PlayerGameLog(player_id=str(player_id), season=season)
        df = log.get_data_frames()[0]
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []


def fetch_team_rosters() -> dict[str, list[dict]]:
    """Fetch all NBA team rosters. Returns {tricode: [{player_id, name, position}, ...]}"""
    from nba_api.stats.static import teams as nba_teams

    rosters = {}
    for team in nba_teams.get_teams():
        time.sleep(NBA_API_DELAY)
        team_id = team["id"]
        tricode = team["abbreviation"]
        try:
            roster = CommonTeamRoster(team_id=str(team_id))
            df = roster.get_data_frames()[0]
            players = []
            for _, row in df.iterrows():
                pos = row.get("POSITION", "")
                if "Guard" in pos or pos in ("G", "G-F"):
                    pos_short = "G"
                elif "Forward" in pos or pos in ("F", "F-G", "F-C"):
                    pos_short = "F"
                elif "Center" in pos or pos == "C":
                    pos_short = "C"
                else:
                    pos_short = "F"
                players.append({
                    "id": row["PLAYER_ID"],
                    "name": row["PLAYER"],
                    "team": tricode,
                    "position": pos_short,
                })
            rosters[tricode] = players
        except Exception:
            continue
    return rosters


def fetch_team_defense_stats(season: str = "2025-26") -> list[dict]:
    """Fetch league-wide team defense stats."""
    time.sleep(NBA_API_DELAY)
    try:
        stats = LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Opponent",
        )
        df = stats.get_data_frames()[0]
        results = []
        for _, row in df.iterrows():
            results.append({
                "team": row["TEAM_ABBREVIATION"],
                "def_rating": row.get("DEF_RATING", 0),
                "vs_guards_ttfl_avg": 0,
                "vs_forwards_ttfl_avg": 0,
                "vs_centers_ttfl_avg": 0,
            })
        return results
    except Exception:
        return []


def compute_player_aggregates(game_logs: list[dict]) -> dict:
    """Compute aggregated stats from game log dicts (from game_logs table).

    DNPs (minutes == 0) are excluded from all averages — they reflect absence,
    not performance, and would otherwise drag the rolling means to zero
    (notably during injury stretches).
    """
    empty = {
        "avg_ttfl_l5": 0, "avg_ttfl_l10": 0, "avg_ttfl_l20": 0,
        "avg_ttfl_season": 0, "stddev_ttfl": 0, "home_avg": 0, "away_avg": 0,
        "avg_minutes_l10": 0,
    }
    if not game_logs:
        return empty

    played = [g for g in game_logs if (g.get("minutes") or 0) > 0]
    if not played:
        return empty

    scores = [g["ttfl_score"] for g in played]
    home_scores = [g["ttfl_score"] for g in played if g["is_home"]]
    away_scores = [g["ttfl_score"] for g in played if not g["is_home"]]
    minutes = [g["minutes"] for g in played]

    return {
        "avg_ttfl_l5": float(np.mean(scores[:5])) if len(scores) >= 1 else 0,
        "avg_ttfl_l10": float(np.mean(scores[:10])) if len(scores) >= 1 else 0,
        "avg_ttfl_l20": float(np.mean(scores[:20])) if len(scores) >= 1 else 0,
        "avg_ttfl_season": float(np.mean(scores)),
        "stddev_ttfl": float(np.std(scores)) if len(scores) >= 3 else 0,
        "home_avg": float(np.mean(home_scores)) if home_scores else 0,
        "away_avg": float(np.mean(away_scores)) if away_scores else 0,
        "avg_minutes_l10": float(np.mean(minutes[:10])) if minutes else 0,
    }
