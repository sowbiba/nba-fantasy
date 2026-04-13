# sync/main.py
"""Cron orchestrator. Runs the full sync pipeline:

1. Fetch today's games + yesterday's results
2. Fetch/update player game logs and box scores
3. Fetch injuries from ESPN
4. Compute player aggregates
5. Compute scoring for tonight's players
6. Apply playoff strategy layer
7. Generate argumentaires for top 50
8. Push everything to Supabase
"""
import sys
import time
import traceback
from datetime import date, datetime, timedelta

import numpy as np

from sync import db
from sync.config import NBA_API_DELAY
from sync.fetcher import (
    fetch_today_scoreboard,
    parse_today_games,
    fetch_live_box_score,
    fetch_player_game_logs_nba_api,
    fetch_team_rosters,
    compute_player_aggregates,
)
from sync.injuries import fetch_all_injuries, match_injury_to_player
from sync.scoring import compute_performance_score
from sync.strategy import (
    classify_tiers,
    estimate_remaining_game_days,
    should_burn_elite,
    compute_strategy_adjustment,
)
from sync.advisor import generate_argumentaire, generate_verdict
from sync.ttfl import compute_ttfl_from_game_log


def run_sync():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting sync...")
    client = db.get_client()
    log_id = db.start_sync_log(client)

    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        players_updated = 0

        # --- Step 1: Fetch today's scoreboard ---
        print("  Fetching scoreboard...")
        scoreboard = fetch_today_scoreboard()
        today_games = parse_today_games(scoreboard, today)
        db.upsert_games(client, today_games)
        print(f"  {len(today_games)} games today")

        # --- Step 2: Fetch yesterday's box scores (for actual_score updates) ---
        yesterday_games = db.get_today_games(client, yesterday)
        for game in yesterday_games:
            if game["status"] != "final":
                continue
            print(f"  Fetching box score for {game['id']}...")
            box_players = fetch_live_box_score(game["id"])
            game_logs = []
            for bp in box_players:
                game_logs.append({
                    "player_id": bp["player_id"],
                    "game_id": bp["game_id"],
                    "date": bp["date"],
                    "pts": bp["pts"], "reb": bp["reb"], "ast": bp["ast"],
                    "stl": bp["stl"], "blk": bp["blk"],
                    "fgm": bp["fgm"], "fga": bp["fga"],
                    "tpm": bp["tpm"], "tpa": bp["tpa"],
                    "ftm": bp["ftm"], "fta": bp["fta"],
                    "tov": bp["tov"], "minutes": bp["minutes"],
                    "ttfl_score": bp["ttfl_score"],
                    "is_home": bp["is_home"],
                })
            db.upsert_game_logs(client, game_logs)

        # --- Step 3: Fetch rosters + update players ---
        print("  Fetching rosters...")
        rosters = fetch_team_rosters()
        all_players_list = []
        for tricode, players in rosters.items():
            for p in players:
                all_players_list.append(p)
        db.upsert_players(client, all_players_list)
        players_updated = len(all_players_list)
        print(f"  {players_updated} players updated")

        # --- Step 4: Fetch injuries ---
        print("  Fetching injuries...")
        playing_teams = set()
        for g in today_games:
            playing_teams.add(g["home_team"])
            playing_teams.add(g["away_team"])

        injuries = fetch_all_injuries(list(playing_teams))
        all_players_db = db.get_all_players(client)

        for team_tricode, team_injuries in injuries.items():
            team_players = [p for p in all_players_db if p["team"] == team_tricode]
            for inj in team_injuries:
                player_id = match_injury_to_player(inj["name"], team_players)
                if player_id:
                    db.upsert_players(client, [{
                        "id": player_id,
                        "injury_status": inj["status"],
                        "injury_detail": inj["detail"],
                    }])

        # Clear injuries for players not in injury report
        for p in all_players_db:
            if p["team"] in playing_teams:
                team_inj_names = [
                    i["name"].lower()
                    for i in injuries.get(p["team"], [])
                ]
                is_injured = any(
                    p["name"].lower().split()[-1] in name
                    for name in team_inj_names
                )
                if not is_injured and p.get("injury_status"):
                    db.upsert_players(client, [{
                        "id": p["id"],
                        "injury_status": None,
                        "injury_detail": None,
                    }])

        # --- Step 5: Update player aggregates for tonight's players ---
        print("  Computing player aggregates...")
        all_players_db = db.get_all_players(client)
        tonight_player_ids = set()
        for g in today_games:
            for p in all_players_db:
                if p["team"] in (g["home_team"], g["away_team"]):
                    tonight_player_ids.add(p["id"])

        for pid in tonight_player_ids:
            logs = db.get_player_game_logs(client, pid, limit=20)
            if not logs:
                nba_logs = fetch_player_game_logs_nba_api(pid)
                if nba_logs:
                    game_log_rows = []
                    for nl in nba_logs[:20]:
                        ttfl = compute_ttfl_from_game_log(nl)
                        game_log_rows.append({
                            "player_id": pid,
                            "game_id": nl.get("Game_ID", f"unknown_{pid}_{nl.get('GAME_DATE', '')}"),
                            "date": nl.get("GAME_DATE", ""),
                            "pts": nl.get("PTS", 0), "reb": nl.get("REB", 0),
                            "ast": nl.get("AST", 0), "stl": nl.get("STL", 0),
                            "blk": nl.get("BLK", 0),
                            "fgm": nl.get("FGM", 0), "fga": nl.get("FGA", 0),
                            "tpm": nl.get("FG3M", 0), "tpa": nl.get("FG3A", 0),
                            "ftm": nl.get("FTM", 0), "fta": nl.get("FTA", 0),
                            "tov": nl.get("TOV", 0),
                            "minutes": nl.get("MIN", 0),
                            "ttfl_score": ttfl,
                            "is_home": "vs." in nl.get("MATCHUP", ""),
                        })
                    db.upsert_game_logs(client, game_log_rows)
                    logs = game_log_rows

            if logs:
                aggs = compute_player_aggregates(logs)
                aggs["id"] = pid
                aggs["updated_at"] = datetime.utcnow().isoformat()
                db.upsert_players(client, [aggs])

        # --- Step 6: Score tonight's players ---
        print("  Scoring players...")
        all_players_db = db.get_all_players(client)
        picked_ids = db.get_picked_player_ids(client, mode="playoffs")
        active_series = db.get_active_series(client)

        scored_players = []
        for g in today_games:
            if g["status"] == "final":
                continue
            for p in all_players_db:
                if p["team"] not in (g["home_team"], g["away_team"]):
                    continue
                if p["id"] in picked_ids:
                    continue
                if p.get("injury_status") in ("Out", "Doubtful"):
                    continue

                is_home = p["team"] == g["home_team"]
                opponent = g["away_team"] if is_home else g["home_team"]
                opp_defense = db.get_team_defense(client, opponent)

                league_avg = 40
                opp_ttfl = league_avg
                if opp_defense:
                    if p["position"] == "G":
                        pos_key = "vs_guards_ttfl_avg"
                    elif p["position"] == "F":
                        pos_key = "vs_forwards_ttfl_avg"
                    else:
                        pos_key = "vs_centers_ttfl_avg"
                    opp_ttfl = opp_defense.get(pos_key, league_avg) or league_avg

                logs = db.get_player_game_logs(client, p["id"], limit=10)
                recent_scores = [l["ttfl_score"] for l in logs]

                if logs:
                    last_game_date = logs[0].get("date", "")
                    try:
                        last_dt = datetime.strptime(str(last_game_date), "%Y-%m-%d").date()
                        days_rest = (date.today() - last_dt).days - 1
                    except (ValueError, TypeError):
                        days_rest = 2
                else:
                    days_rest = 2

                perf_score = compute_performance_score(
                    avg_l5=p.get("avg_ttfl_l5", 0) or 0,
                    avg_l10=p.get("avg_ttfl_l10", 0) or 0,
                    avg_l20=p.get("avg_ttfl_l20", 0) or 0,
                    opponent_ttfl_at_position=opp_ttfl,
                    league_avg_ttfl_at_position=league_avg,
                    home_avg=p.get("home_avg", 0) or 0,
                    away_avg=p.get("away_avg", 0) or 0,
                    season_avg=p.get("avg_ttfl_season", 0) or 0,
                    is_home=is_home,
                    days_rest=days_rest,
                    recent_scores=recent_scores,
                    stddev=p.get("stddev_ttfl", 0) or 0,
                )

                scored_players.append({
                    "player": p, "game": g, "perf_score": perf_score,
                    "is_home": is_home, "opponent": opponent,
                    "days_rest": days_rest, "recent_scores": recent_scores,
                })

        # --- Step 7: Apply playoff strategy ---
        print("  Applying strategy layer...")
        available_scores = [(sp["player"]["id"], sp["perf_score"]) for sp in scored_players]
        tiers = classify_tiers(available_scores)

        current_round = max((s["round"] for s in active_series), default=1)
        game_days_remaining = estimate_remaining_game_days(active_series, current_round)
        elites_remaining = sum(1 for t in tiers.values() if t == "elite")

        for sp in scored_players:
            pid = sp["player"]["id"]
            tier = tiers.get(pid, "filler")
            sp["tier"] = tier

            game = sp["game"]
            series = None
            for s in active_series:
                teams = {s["home_team"], s["away_team"]}
                if game["home_team"] in teams and game["away_team"] in teams:
                    series = s
                    break

            series_score = (series["home_wins"], series["away_wins"]) if series else (0, 0)

            strategy_score = compute_strategy_adjustment(
                perf_score=sp["perf_score"], tier=tier, is_home=sp["is_home"],
                series_score=series_score, elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
            )
            sp["strategy_score"] = strategy_score
            sp["estimated_score"] = strategy_score
            sp["series_score"] = series_score
            sp["game_number"] = game.get("game_number", 0) or 0

        scored_players.sort(key=lambda x: x["estimated_score"], reverse=True)
        top_50 = scored_players[:50]

        # --- Step 8: Generate argumentaires ---
        print("  Generating argumentaires...")
        recommendations = []
        for rank, sp in enumerate(top_50, start=1):
            p = sp["player"]
            logs = sp["recent_scores"]
            floor_val = min(logs) if logs else 0
            ceiling_val = max(logs) if logs else 0

            same_pos = [s for s in scored_players if s["player"]["position"] == p["position"]]
            same_pos.sort(key=lambda x: x["perf_score"], reverse=True)
            matchup_rank = next(
                (i for i, s in enumerate(same_pos, 1) if s["player"]["id"] == p["id"]), 15,
            )

            teammate_out = None
            for tp in all_players_db:
                if tp["team"] == p["team"] and tp.get("injury_status") == "Out":
                    if (tp.get("usage_rate", 0) or 0) > 20:
                        teammate_out = tp["name"]
                        break

            context = {
                "player_name": p["name"], "team": p["team"], "opponent": sp["opponent"],
                "is_home": sp["is_home"],
                "avg_l5": p.get("avg_ttfl_l5", 0) or 0,
                "avg_season": p.get("avg_ttfl_season", 0) or 0,
                "matchup_rank": matchup_rank,
                "matchup_position": {"G": "guards", "F": "forwards", "C": "centers"}.get(p["position"], "forwards"),
                "series_score": sp["series_score"], "game_number": sp["game_number"],
                "tier": sp["tier"], "elites_remaining": elites_remaining,
                "game_days_remaining": game_days_remaining, "days_rest": sp["days_rest"],
                "stddev": p.get("stddev_ttfl", 0) or 0,
                "floor": floor_val, "ceiling": ceiling_val,
                "injury_status": p.get("injury_status"), "teammate_out": teammate_out,
            }

            pros, cons = generate_argumentaire(context)

            burn = should_burn_elite(
                tonight_score=sp["estimated_score"],
                best_future_score=sp["estimated_score"] * 0.95,
                elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
            )
            verdict = generate_verdict(
                should_burn=burn, tier=sp["tier"],
                tonight_score=sp["estimated_score"],
                best_future_description="prochain match à domicile",
            )

            tags = []
            if sp["is_home"]:
                tags.append("home")
            if p.get("avg_ttfl_l5", 0) and p.get("avg_ttfl_season", 0):
                if p["avg_ttfl_l5"] > p["avg_ttfl_season"] * 1.1:
                    tags.append("hot")
            if (p.get("stddev_ttfl", 0) or 0) > 15:
                tags.append("volatile")
            if rank <= 3:
                tags.append("reco_du_soir")

            recommendations.append({
                "date": today.isoformat(), "player_id": p["id"], "rank": rank,
                "estimated_score": round(sp["estimated_score"], 1),
                "perf_score": round(sp["perf_score"], 1),
                "matchup_score": round(sp.get("matchup_score", 0), 1),
                "strategy_score": round(sp.get("strategy_score", 0), 1),
                "pros": pros, "cons": cons, "verdict": verdict,
                "tier": sp["tier"], "tags": tags,
                "computed_at": datetime.utcnow().isoformat(),
            })

        # --- Step 9: Push to Supabase ---
        print(f"  Pushing {len(recommendations)} recommendations...")
        db.replace_recommendations(client, recommendations, today)

        db.finish_sync_log(client, log_id, players_updated)
        print(f"[{datetime.now():%H:%M}] Sync complete! {len(recommendations)} players scored.")

    except Exception as e:
        traceback.print_exc()
        db.fail_sync_log(client, log_id, str(e))
        print(f"[{datetime.now():%H:%M}] Sync FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_sync()
