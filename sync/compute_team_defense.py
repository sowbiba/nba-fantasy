"""Compute team defensive TTFL allowed per position from game_logs.

For each team, for each position (G/F/C), aggregate the TTFL score of the
OPPOSING players at that position across all their games. The result is
stored in team_defense.vs_<position>s_ttfl_avg.

This populates the 25% matchup factor that's currently falling back to
league_avg everywhere.
"""
from datetime import datetime

import numpy as np

from sync.db import get_client


def compute_and_push():
    c = get_client()

    print("Loading players...")
    players = c.table("players").select("id, team, position").execute().data
    player_by_id = {p["id"]: p for p in players}

    # All game_logs (can be lots of rows — paginate)
    print("Loading game_logs...")
    all_logs: list[dict] = []
    offset = 0
    page = 1000
    while True:
        res = c.table("game_logs").select(
            "player_id, game_id, ttfl_score, is_home"
        ).range(offset, offset + page - 1).execute()
        chunk = res.data
        if not chunk:
            break
        all_logs.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    print(f"  {len(all_logs)} game_logs")

    # Load games to know opponents
    print("Loading games...")
    games_res = c.table("games").select("id, home_team, away_team").execute()
    games_by_id = {g["id"]: g for g in games_res.data}

    # Aggregate: for each team (= opponent), accumulate TTFL of the OTHER team's players by position
    # opponent_ttfl[team] = {"G": [scores], "F": [...], "C": [...]}
    per_team: dict[str, dict[str, list[float]]] = {}

    for log in all_logs:
        pid = log["player_id"]
        gid = log["game_id"]
        player = player_by_id.get(pid)
        game = games_by_id.get(gid)
        if not player or not game:
            continue

        player_team = player["team"]
        position = player["position"]
        if position not in ("G", "F", "C"):
            continue

        # Opponent = the OTHER team in this game
        if game["home_team"] == player_team:
            opponent = game["away_team"]
        elif game["away_team"] == player_team:
            opponent = game["home_team"]
        else:
            # Orphan game_log (player team changed since, or UNK game)
            continue

        if opponent in ("UNK", "TBD", ""):
            continue

        per_team.setdefault(opponent, {"G": [], "F": [], "C": []})
        per_team[opponent][position].append(log["ttfl_score"])

    # Compute averages and push
    print("Pushing team defense averages...")
    rows = []
    for team, pos_scores in per_team.items():
        row = {
            "team": team,
            "vs_guards_ttfl_avg": float(np.mean(pos_scores["G"])) if pos_scores["G"] else 0,
            "vs_forwards_ttfl_avg": float(np.mean(pos_scores["F"])) if pos_scores["F"] else 0,
            "vs_centers_ttfl_avg": float(np.mean(pos_scores["C"])) if pos_scores["C"] else 0,
            "def_rating": 0,  # populated separately by fetcher.fetch_team_defense_stats
            "updated_at": datetime.utcnow().isoformat(),
        }
        rows.append(row)

    # Upsert all at once
    if rows:
        c.table("team_defense").upsert(rows, on_conflict="team").execute()

    print(f"Done — {len(rows)} teams updated.")
    # Show a sample
    for r in sorted(rows, key=lambda x: x["vs_centers_ttfl_avg"], reverse=True)[:5]:
        print(
            f"  {r['team']}: G={r['vs_guards_ttfl_avg']:.1f} "
            f"F={r['vs_forwards_ttfl_avg']:.1f} C={r['vs_centers_ttfl_avg']:.1f}"
        )


if __name__ == "__main__":
    compute_and_push()
