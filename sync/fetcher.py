# sync/fetcher.py
"""Fetch NBA data from cdn.nba.com and nba_api.

Collects: today's games, box scores, player game logs,
team rosters, team defense stats, playoff series.
"""
import time
from datetime import date, datetime, timedelta

from nba_api.stats.endpoints import (
    BoxScoreMatchupsV3,
    BoxScoreTraditionalV3,
    LeagueDashTeamStats,
    CommonTeamRoster,
    PlayerGameLog,
    ScoreboardV3,
)
from nba_api.live.nba.endpoints import BoxScore, ScoreBoard
from nba_api.live.nba.library import http as _live_http
from nba_api.stats.library import http as _stats_http

from sync.config import NBA_API_DELAY
from sync.ttfl import compute_ttfl_score

import numpy as np

# Akamai on cdn.nba.com / stats.nba.com rejects requests without a Referer
# pointing at www.nba.com (HTTP 403 "Access Denied"). nba_api's default
# headers omit Referer, so we inject it here.
_live_http.NBALiveHTTP.headers = {
    **_live_http.NBALiveHTTP.headers,
    "Referer": "https://www.nba.com/",
}
_stats_http.NBAStatsHTTP.headers = {
    **_stats_http.NBAStatsHTTP.headers,
    "Referer": "https://www.nba.com/",
}


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


def _parse_v3_minutes(min_str: str | None) -> int:
    """Parse 'mm:ss' from BoxScoreTraditionalV3 into integer minutes (DNP -> 0)."""
    if not min_str or ":" not in min_str:
        return 0
    try:
        return int(min_str.split(":")[0])
    except (ValueError, IndexError):
        return 0


def fetch_box_score_stats_api(
    game_id: str,
    home_tricode: str | None = None,
    game_date: str | None = None,
) -> list[dict]:
    """Persistent box-score fallback via NBA Stats API (BoxScoreTraditionalV3).

    The CDN live boxscore JSON is only kept for a few hours after the final
    buzzer. Once it's purged, the stats endpoint is the only way to recover
    the player rows. Returns the same shape as `fetch_live_box_score`.
    """
    time.sleep(NBA_API_DELAY)
    try:
        box = BoxScoreTraditionalV3(game_id=game_id)
        df = box.player_stats.get_data_frame()
    except Exception:
        return []

    if df.empty:
        return []

    # Determine home team — pass-in is authoritative (we already store it on
    # the games table). If missing, fall back to the team_stats endpoint
    # which lists home/away teams in order.
    home_resolved = home_tricode
    if not home_resolved:
        try:
            team_df = box.team_stats.get_data_frame()
            # team_stats rows are ordered: home first, then away.
            if not team_df.empty:
                home_resolved = team_df.iloc[0]["teamTricode"]
        except Exception:
            home_resolved = None

    players = []
    for _, row in df.iterrows():
        minutes = _parse_v3_minutes(row.get("minutes"))
        pts = int(row.get("points") or 0)
        reb = int(row.get("reboundsTotal") or 0)
        ast = int(row.get("assists") or 0)
        stl = int(row.get("steals") or 0)
        blk = int(row.get("blocks") or 0)
        fgm = int(row.get("fieldGoalsMade") or 0)
        fga = int(row.get("fieldGoalsAttempted") or 0)
        tpm = int(row.get("threePointersMade") or 0)
        tpa = int(row.get("threePointersAttempted") or 0)
        ftm = int(row.get("freeThrowsMade") or 0)
        fta = int(row.get("freeThrowsAttempted") or 0)
        tov = int(row.get("turnovers") or 0)
        ttfl = compute_ttfl_score(
            pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov
        )
        is_home = (
            home_resolved is not None and row.get("teamTricode") == home_resolved
        )
        players.append({
            "player_id": int(row["personId"]),
            "player_name": f"{row['firstName']} {row['familyName']}",
            "team": row.get("teamTricode") or "",
            "game_id": str(row.get("gameId") or game_id),
            "date": game_date or "",
            "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
            "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa,
            "ftm": ftm, "fta": fta, "tov": tov,
            "minutes": minutes,
            "ttfl_score": ttfl,
            "is_home": is_home,
        })
    return players


def fetch_live_box_score(
    game_id: str,
    home_tricode: str | None = None,
    game_date: str | None = None,
) -> list[dict]:
    """Fetch box score for a finished/live game. Returns player stat dicts.

    Tries the CDN live endpoint first (instant, no rate limit). Falls back to
    the persistent NBA Stats API when the CDN has purged the JSON — typically
    a few hours after the final buzzer.
    """
    try:
        box = BoxScore(game_id=game_id)
        data = box.get_dict()["game"]
    except Exception:
        return fetch_box_score_stats_api(game_id, home_tricode, game_date)

    players = []
    cdn_game_date = data.get("gameTimeUTC", "")[:10] or game_date

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
                "date": cdn_game_date,
                "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
                "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa,
                "ftm": ftm, "fta": fta, "tov": tov,
                "minutes": minutes,
                "ttfl_score": ttfl,
                "is_home": is_home,
            })

    # CDN sometimes returns the game shell with empty `players` arrays once
    # it has started purging. Fall back to the stats API in that case.
    if not players:
        return fetch_box_score_stats_api(game_id, home_tricode, game_date)

    return players


def fetch_box_score_matchups(game_id: str) -> list[dict]:
    """Per-pair matchup rows for a finished game.

    Each row is one (offensive_player, primary_defender) pairing inside
    this game, with matchup minutes and the offensive line the player
    produced while that defender was on him. Source: NBA Stats
    BoxScoreMatchupsV3 (post-game, persistent — unlike the live CDN).
    """
    time.sleep(NBA_API_DELAY)
    try:
        box = BoxScoreMatchupsV3(game_id=game_id)
        df = box.player_stats.get_data_frame()
    except Exception:
        return []

    if df.empty:
        return []

    rows = []
    for _, r in df.iterrows():
        seconds = float(r.get("matchupMinutesSort") or 0)
        rows.append({
            "game_id": str(r.get("gameId") or game_id),
            "off_team": r.get("teamTricode") or "",
            "off_player_id": int(r["personIdOff"]),
            "off_player_name": f"{r['firstNameOff']} {r['familyNameOff']}",
            "def_player_id": int(r["personIdDef"]),
            "def_player_name": f"{r['firstNameDef']} {r['familyNameDef']}",
            "matchup_seconds": seconds,
            "partial_possessions": float(r.get("partialPossessions") or 0),
            "player_points": int(r.get("playerPoints") or 0),
            "matchup_assists": int(r.get("matchupAssists") or 0),
            "matchup_turnovers": int(r.get("matchupTurnovers") or 0),
            "matchup_blocks": int(r.get("matchupBlocks") or 0),
            "matchup_fgm": int(r.get("matchupFieldGoalsMade") or 0),
            "matchup_fga": int(r.get("matchupFieldGoalsAttempted") or 0),
            "matchup_tpm": int(r.get("matchupThreePointersMade") or 0),
            "matchup_tpa": int(r.get("matchupThreePointersAttempted") or 0),
            "matchup_ftm": int(r.get("matchupFreeThrowsMade") or 0),
            "matchup_fta": int(r.get("matchupFreeThrowsAttempted") or 0),
        })
    return rows


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
