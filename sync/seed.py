"""Seed script: load historical game logs for playoff teams.

Fetches the last 20 game logs for every player on teams currently in the playoffs,
computes TTFL scores, pushes to Supabase, and updates player aggregates.
"""
import time
from datetime import datetime

from sync import db
from sync.config import NBA_API_DELAY
from sync.fetcher import (
    fetch_player_game_logs_nba_api,
    compute_player_aggregates,
)
from sync.ttfl import compute_ttfl_from_game_log

# 2025-26 playoff teams + play-in teams (all 20)
PLAYOFF_TEAMS = [
    "BOS", "CLE", "NYK", "MIL", "IND", "DET", "ORL", "ATL", "PHI", "MIA", "CHA",  # East
    "OKC", "DEN", "MIN", "LAL", "HOU", "MEM", "LAC", "GSW", "SAS", "POR", "PHX",  # West
]


def seed():
    print(f"[{datetime.now():%H:%M}] Seeding game logs for playoff teams...")
    client = db.get_client()

    all_players = db.get_all_players(client)
    playoff_players = [p for p in all_players if p["team"] in PLAYOFF_TEAMS]
    print(f"  {len(playoff_players)} players on playoff teams")

    total = len(playoff_players)
    for i, p in enumerate(playoff_players, 1):
        pid = p["id"]
        name = p["name"]

        # Skip if we already have logs
        existing = db.get_player_game_logs(client, pid, limit=1)
        if existing:
            continue

        print(f"  [{i}/{total}] Fetching logs for {name} ({p['team']})...")
        nba_logs = fetch_player_game_logs_nba_api(pid, season="2025-26")

        if not nba_logs:
            continue

        game_log_rows = []
        for nl in nba_logs[:20]:
            try:
                ttfl = compute_ttfl_from_game_log(nl)
            except (KeyError, TypeError):
                continue

            matchup = nl.get("MATCHUP", "")
            game_log_rows.append({
                "player_id": pid,
                "game_id": str(nl.get("Game_ID", f"hist_{pid}_{nl.get('GAME_DATE', '')}")),
                "date": nl.get("GAME_DATE", ""),
                "pts": int(nl.get("PTS", 0) or 0),
                "reb": int(nl.get("REB", 0) or 0),
                "ast": int(nl.get("AST", 0) or 0),
                "stl": int(nl.get("STL", 0) or 0),
                "blk": int(nl.get("BLK", 0) or 0),
                "fgm": int(nl.get("FGM", 0) or 0),
                "fga": int(nl.get("FGA", 0) or 0),
                "tpm": int(nl.get("FG3M", 0) or 0),
                "tpa": int(nl.get("FG3A", 0) or 0),
                "ftm": int(nl.get("FTM", 0) or 0),
                "fta": int(nl.get("FTA", 0) or 0),
                "tov": int(nl.get("TOV", 0) or 0),
                "minutes": int(nl.get("MIN", 0) or 0),
                "ttfl_score": ttfl,
                "is_home": "vs." in matchup,
            })

        if game_log_rows:
            # Ensure game records exist (FK constraint)
            for gl, nl in zip(game_log_rows, nba_logs[:20]):
                game_id = gl["game_id"]
                existing_game = client.table("games").select("id").eq("id", game_id).execute()
                if not existing_game.data:
                    matchup = nl.get("MATCHUP", "")
                    # Parse "ATL vs. BOS" (home) or "ATL @ BOS" (away)
                    if "vs." in matchup:
                        parts = matchup.split(" vs. ")
                        home_team = parts[0].strip()
                        away_team = parts[1].strip() if len(parts) > 1 else "UNK"
                    elif "@" in matchup:
                        parts = matchup.split(" @ ")
                        away_team = parts[0].strip()  # player's team is away
                        home_team = parts[1].strip() if len(parts) > 1 else "UNK"
                    else:
                        home_team = p["team"] if gl["is_home"] else "UNK"
                        away_team = "UNK" if gl["is_home"] else p["team"]
                    client.table("games").insert({
                        "id": game_id,
                        "date": gl["date"],
                        "home_team": home_team,
                        "away_team": away_team,
                        "status": "final",
                    }).execute()

            db.upsert_game_logs(client, game_log_rows)

            # Update aggregates (use update, not upsert, to preserve name/team/position)
            aggs = compute_player_aggregates(game_log_rows)
            aggs["updated_at"] = datetime.now(datetime.now().astimezone().tzinfo).isoformat()
            client.table("players").update(aggs).eq("id", pid).execute()
            print(f"    → {len(game_log_rows)} logs, avg TTFL: {aggs['avg_ttfl_season']:.1f}")

    print(f"[{datetime.now():%H:%M}] Seed complete!")


if __name__ == "__main__":
    seed()
