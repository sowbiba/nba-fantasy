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
from datetime import UTC, date, datetime, timedelta

import numpy as np

from sync import db
from sync.config import MIN_MINUTES_L10, NBA_API_DELAY
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
    TEAM_POTENTIAL_UNKNOWN,
    classify_tiers,
    compute_reservation_penalty,
    compute_strategy_adjustment,
    compute_team_potential_scores,
    elimination_risk,
    estimate_remaining_game_days,
    should_burn_elite,
)
from sync.advisor import generate_argumentaire, generate_verdict
from sync.ttfl import compute_ttfl_from_game_log
from sync.future import compute_best_future_opportunity


# User watchlist ranking boosts, escalating with elimination pressure. See
# /home/isow/.claude/plans/greedy-swinging-wirth.md for rationale.
WATCHLIST_BASE = {1: 0.12, 2: 0.07, 3: 0.03}
WATCHLIST_ELIM_BONUS = {"critical": 0.35, "high": 0.15, "none": 0.0}
# Challenger Game 3 at home after 0-2 deficit — watchlist players only.
GAME3_SURGE_MULTIPLIER = 1.12


def run_sync():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting sync...")
    client = db.get_client()
    log_id = db.start_sync_log(client)

    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        players_updated = 0

        # --- Step 1: Fetch today's scoreboard ---
        # The scoreboard reflects the NBA's current "game day" which can lag
        # behind our local date (play-in nights tipping off Friday night ET
        # are still on the Friday scoreboard well into Saturday morning). We
        # upsert whatever the scoreboard says — tagged with *its* gameDate —
        # then rely on the DB (fed by load_schedule.py) to know what games
        # actually happen on `today`.
        print("  Fetching scoreboard...")
        scoreboard = fetch_today_scoreboard()
        scoreboard_games = parse_today_games(scoreboard, today)
        db.upsert_games(client, scoreboard_games)
        print(f"  {len(scoreboard_games)} games on scoreboard (date={scoreboard.get('gameDate') or today})")

        # Step 1b: refresh playoff series + schedule (safe to re-run, upserts)
        try:
            from sync.load_schedule import load as load_schedule_fn
            load_schedule_fn(days_ahead=30)
        except Exception as e:
            print(f"  (schedule load skipped: {e})")

        try:
            from sync.seed_playoffs import seed as seed_playoffs_fn
            seed_playoffs_fn()
        except Exception as e:
            print(f"  (playoff seed skipped: {e})")

        # Step 1c: once per day (around 7h), refresh team defense stats
        # from the latest game_logs so matchup factor stays accurate.
        if datetime.now().hour < 10:
            try:
                from sync.compute_team_defense import compute_and_push
                compute_and_push()
            except Exception as e:
                print(f"  (team defense refresh skipped: {e})")

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

        # Step 2b: update actual_score on picks now that box scores are final.
        # Match on (player_id, game_id) — the game_id is stable whereas the
        # pick date vs game_log date can differ (NBA logs use the finish
        # date in UTC, which is the next calendar day for late West Coast
        # games).
        unscored_picks = client.table("picks").select(
            "id, player_id, game_id, date"
        ).filter("actual_score", "is", "null").execute().data or []
        updated_picks = 0
        for pick in unscored_picks:
            log_res = client.table("game_logs").select("ttfl_score").eq(
                "player_id", pick["player_id"]
            ).eq("game_id", pick["game_id"]).execute()
            if log_res.data:
                ttfl = log_res.data[0]["ttfl_score"]
                client.table("picks").update({
                    "actual_score": ttfl
                }).eq("id", pick["id"]).execute()
                updated_picks += 1
                continue
            # No game_log row. If the game is final, the picked player
            # wasn't even in the box score (not dressed / inactive list).
            # That's a DNP → lock in 0 so the pick stops showing as "—".
            game_res = client.table("games").select("status").eq(
                "id", pick["game_id"]
            ).execute()
            if game_res.data and game_res.data[0]["status"] == "final":
                client.table("picks").update({
                    "actual_score": 0
                }).eq("id", pick["id"]).execute()
                updated_picks += 1
        if updated_picks > 0:
            print(f"  Updated {updated_picks} pick(s) with actual score.")

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

        # Games happening today (local), fetched from the DB — this is what
        # Steps 4/5/6 iterate on. Decoupled from the scoreboard so that a
        # stale scoreboard can't wipe out tonight's recos.
        today_games = db.get_today_games(client, today)
        print(f"  {len(today_games)} games in DB for {today}")

        # --- Step 4: Fetch injuries (all teams, not just tonight's) ---
        print("  Fetching injuries...")
        playing_teams = set()
        for g in today_games:
            playing_teams.add(g["home_team"])
            playing_teams.add(g["away_team"])

        injuries = fetch_all_injuries()
        all_players_db = db.get_all_players(client)

        for team_tricode, team_injuries in injuries.items():
            team_players = [p for p in all_players_db if p["team"] == team_tricode]
            for inj in team_injuries:
                player_id = match_injury_to_player(inj["name"], team_players)
                if player_id:
                    update_payload = {
                        "injury_status": inj["status"],
                        "injury_detail": inj["detail"],
                    }
                    # Optional enriched fields (require DB migration)
                    if inj.get("short_comment"):
                        update_payload["injury_short_comment"] = inj["short_comment"]
                    if inj.get("return_date"):
                        update_payload["injury_return_date"] = inj["return_date"]
                    if inj.get("updated_at"):
                        update_payload["injury_updated_at"] = inj["updated_at"]
                    try:
                        client.table("players").update(update_payload).eq("id", player_id).execute()
                    except Exception:
                        # Fallback if enriched columns don't exist yet
                        client.table("players").update({
                            "injury_status": inj["status"],
                            "injury_detail": inj["detail"],
                        }).eq("id", player_id).execute()

        # Clear injuries for players not in injury report (all teams)
        for p in all_players_db:
            team_inj_names = [
                i["name"].lower()
                for i in injuries.get(p["team"], [])
            ]
            is_injured = any(
                p["name"].lower().split()[-1] in name
                for name in team_inj_names
            )
            if not is_injured and p.get("injury_status"):
                clear_payload = {
                    "injury_status": None,
                    "injury_detail": None,
                }
                try:
                    clear_payload["injury_short_comment"] = None
                    clear_payload["injury_return_date"] = None
                    client.table("players").update(clear_payload).eq("id", p["id"]).execute()
                except Exception:
                    client.table("players").update({
                        "injury_status": None,
                        "injury_detail": None,
                    }).eq("id", p["id"]).execute()

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
                    # Find player team for FK game creation
                    player_team = next((p["team"] for p in all_players_db if p["id"] == pid), "UNK")

                    game_log_rows = []
                    for nl in nba_logs[:20]:
                        ttfl = compute_ttfl_from_game_log(nl)
                        game_id = str(nl.get("Game_ID", f"unknown_{pid}_{nl.get('GAME_DATE', '')}"))
                        game_date = nl.get("GAME_DATE", "")
                        matchup = nl.get("MATCHUP", "")
                        is_home = "vs." in matchup

                        # Ensure game exists (FK constraint)
                        existing = client.table("games").select("id").eq("id", game_id).execute()
                        if not existing.data:
                            # Parse opponent from MATCHUP e.g. "DEN vs. OKC" or "DEN @ OKC"
                            if "vs." in matchup:
                                parts = matchup.split(" vs. ")
                                home_team = parts[0].strip()
                                away_team = parts[1].strip() if len(parts) > 1 else "UNK"
                            elif "@" in matchup:
                                parts = matchup.split(" @ ")
                                away_team = parts[0].strip()
                                home_team = parts[1].strip() if len(parts) > 1 else "UNK"
                            else:
                                home_team = player_team if is_home else "UNK"
                                away_team = "UNK" if is_home else player_team
                            client.table("games").insert({
                                "id": game_id,
                                "date": game_date,
                                "home_team": home_team,
                                "away_team": away_team,
                                "status": "final",
                            }).execute()

                        game_log_rows.append({
                            "player_id": pid,
                            "game_id": game_id,
                            "date": game_date,
                            "pts": nl.get("PTS", 0), "reb": nl.get("REB", 0),
                            "ast": nl.get("AST", 0), "stl": nl.get("STL", 0),
                            "blk": nl.get("BLK", 0),
                            "fgm": nl.get("FGM", 0), "fga": nl.get("FGA", 0),
                            "tpm": nl.get("FG3M", 0), "tpa": nl.get("FG3A", 0),
                            "ftm": nl.get("FTM", 0), "fta": nl.get("FTA", 0),
                            "tov": nl.get("TOV", 0),
                            "minutes": nl.get("MIN", 0),
                            "ttfl_score": ttfl,
                            "is_home": is_home,
                        })
                    db.upsert_game_logs(client, game_log_rows)
                    logs = game_log_rows

            if logs:
                aggs = compute_player_aggregates(logs)
                aggs["updated_at"] = datetime.now(UTC).isoformat()
                client.table("players").update(aggs).eq("id", pid).execute()

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
                # Rotation-fringe cutoff — see sync/weekly_plan.py for the
                # same gate. Avoids surfacing benchers whose L5 is inflated
                # by a single garbage-time blowout. Skip when the column
                # is still at the default 0 (pre-backfill) to stay graceful.
                avg_min_l10 = p.get("avg_minutes_l10", 0) or 0
                if 0 < avg_min_l10 < MIN_MINUTES_L10:
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

        # Load user forecasts (optional, table may not exist yet)
        forecast_map: dict[int, dict] = {}
        try:
            fc_rows = client.table("series_forecast").select(
                "series_id, winner_team, expected_games"
            ).execute().data or []
            forecast_map = {r["series_id"]: r for r in fc_rows}
            if forecast_map:
                print(f"  {len(forecast_map)} series forecasts loaded")
        except Exception as e:
            print(f"  (series_forecast table missing, skipping: {e})")

        current_round = max((s["round"] for s in active_series), default=1)
        game_days_remaining = estimate_remaining_game_days(
            active_series, current_round, forecasts=forecast_map
        )
        elites_remaining = sum(1 for t in tiers.values() if t == "elite")
        team_potential = compute_team_potential_scores(
            active_series, forecasts=forecast_map
        )

        # Watchlist: user-flagged must-play players (priority 1..3). Wrapped
        # in try/except so the sync still works before the migration is applied.
        watchlist_map: dict[int, int] = {}
        try:
            wl_rows = client.table("player_watchlist").select(
                "player_id, priority"
            ).execute().data or []
            watchlist_map = {r["player_id"]: r["priority"] for r in wl_rows}
            if watchlist_map:
                print(f"  {len(watchlist_map)} watchlist entries loaded")
        except Exception as e:
            print(f"  (watchlist table missing, skipping boost: {e})")

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

            # Determine elimination risk from the player's perspective
            player_series_is_home = bool(
                series and sp["player"]["team"] == series["home_team"]
            )
            elim = elimination_risk(series_score, player_series_is_home) if series else "none"

            strategy_score = compute_strategy_adjustment(
                perf_score=sp["perf_score"], tier=tier, is_home=sp["is_home"],
                series_score=series_score, elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
                elimination=elim,
            )

            # Reservation tax (elite preservation for deeper rounds). Bypassed
            # when elimination is critical: the player might be gone tomorrow,
            # no reason to save him.
            reservation = 0.0
            if elim != "critical":
                season_avg = sp["player"].get("avg_ttfl_season", 0) or 0
                round_num = series["round"] if series else 1
                tp = team_potential.get(
                    sp["player"]["team"], TEAM_POTENTIAL_UNKNOWN
                )
                reservation = compute_reservation_penalty(
                    player_season_avg=season_avg,
                    team_potential=tp,
                    round_num=round_num,
                )

            # Watchlist boost — your flagged must-plays rise in the ranking,
            # more so as their team approaches elimination.
            priority = watchlist_map.get(pid)
            base_boost = WATCHLIST_BASE.get(priority, 0) if priority else 0
            elim_boost = WATCHLIST_ELIM_BONUS.get(elim, 0) if priority else 0
            watchlist_boost = base_boost + elim_boost

            # Challenger's Game 3 at home after an 0-2 deficit — franchise
            # players in must-win mode on their first home floor.
            hw, aw = series_score
            player_wins = hw if player_series_is_home else aw
            opponent_wins = aw if player_series_is_home else hw
            game3_surge = bool(
                priority
                and sp["is_home"]
                and game.get("game_number") == 3
                and player_wins == 0
                and opponent_wins == 2
            )
            surge_multiplier = GAME3_SURGE_MULTIPLIER if game3_surge else 1.0

            sp["strategy_score"] = strategy_score
            sp["reservation_penalty"] = reservation
            sp["watchlist_priority"] = priority
            sp["watchlist_boost"] = watchlist_boost
            sp["game3_surge"] = game3_surge
            sp["estimated_score"] = (
                strategy_score
                * (1.0 - reservation)
                * (1.0 + watchlist_boost)
                * surge_multiplier
            )
            sp["series_score"] = series_score
            sp["game_number"] = game.get("game_number", 0) or 0
            sp["elimination"] = elim
            sp["player_series_is_home"] = player_series_is_home

        scored_players.sort(key=lambda x: x["estimated_score"], reverse=True)
        top_50 = scored_players[:50]

        # --- Prefetch for future-opportunity scoring (Step B) ---
        future_window_end = (today + timedelta(days=7)).isoformat()
        future_games_res = client.table("games").select("*").gte(
            "date", today.isoformat()
        ).lte("date", future_window_end).execute()
        future_games = future_games_res.data or []

        team_defense_res = client.table("team_defense").select("*").execute()
        team_defense_cache = {
            row["team"]: row for row in (team_defense_res.data or [])
        }

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

            # Identify impactful teammate(s) who are OUT.
            # "Impactful" = top-3 in their team by season avg TTFL (a proxy for usage).
            team_mates = [
                tp for tp in all_players_db
                if tp["team"] == p["team"] and tp["id"] != p["id"]
            ]
            team_mates.sort(
                key=lambda x: x.get("avg_ttfl_season", 0) or 0, reverse=True
            )
            top3_mates = team_mates[:3]
            teammate_out = None
            for tp in top3_mates:
                if tp.get("injury_status") in ("Out", "Doubtful"):
                    teammate_out = tp["name"]
                    break

            context = {
                "player_name": p["name"], "team": p["team"], "opponent": sp["opponent"],
                "is_home": sp["is_home"],
                "avg_l5": p.get("avg_ttfl_l5", 0) or 0,
                "avg_l10": p.get("avg_ttfl_l10", 0) or 0,
                "avg_season": p.get("avg_ttfl_season", 0) or 0,
                "matchup_rank": matchup_rank,
                "matchup_position": {"G": "guards", "F": "forwards", "C": "centers"}.get(p["position"], "forwards"),
                "series_score": sp["series_score"], "game_number": sp["game_number"],
                "tier": sp["tier"], "elites_remaining": elites_remaining,
                "game_days_remaining": game_days_remaining, "days_rest": sp["days_rest"],
                "stddev": p.get("stddev_ttfl", 0) or 0,
                "floor": floor_val, "ceiling": ceiling_val,
                "injury_status": p.get("injury_status"), "teammate_out": teammate_out,
                "elimination": sp["elimination"],
                "home_avg": p.get("home_avg", 0) or 0,
                "away_avg": p.get("away_avg", 0) or 0,
                "rank": rank,
                "reservation_penalty": sp["reservation_penalty"],
                "watchlist_priority": sp.get("watchlist_priority"),
                "game3_surge": sp.get("game3_surge", False),
            }

            pros, cons = generate_argumentaire(context)

            # Step B: compute real best future opportunity over the next 7 days
            best_future_score, best_future_desc = compute_best_future_opportunity(
                player=p,
                player_recent_scores=sp["recent_scores"],
                future_games=future_games,
                team_defense_cache=team_defense_cache,
                today=today,
                days_ahead=7,
            )
            if best_future_desc is None:
                best_future_desc = "aucun match prévu dans les 7 prochains jours"
                best_future_score = 0.0

            burn = should_burn_elite(
                tonight_score=sp["estimated_score"],
                best_future_score=best_future_score,
                elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
                elimination=sp["elimination"],
            )
            verdict = generate_verdict(
                should_burn=burn, tier=sp["tier"],
                # Narrative score uses strategy_score (pre-reservation) so the
                # "GARDE-LE à 55 pts" verdict surfaces the true expected TTFL
                # tonight, while the ranking/sorting layer still prefers to
                # save Jokic-types (estimated_score applies reservation).
                tonight_score=sp["strategy_score"],
                best_future_description=best_future_desc,
                elimination=sp["elimination"],
                elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
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
            if sp["elimination"] == "critical":
                tags.append("elimination_critical")
            elif sp["elimination"] == "high":
                tags.append("elimination_high")
            if teammate_out:
                tags.append("teammate_out")
            if sp.get("watchlist_priority"):
                tags.append(f"watchlist_p{sp['watchlist_priority']}")
            if sp.get("game3_surge"):
                tags.append("game3_surge")

            recommendations.append({
                "date": today.isoformat(), "player_id": p["id"], "rank": rank,
                "estimated_score": round(sp["estimated_score"], 1),
                "perf_score": round(sp["perf_score"], 1),
                "matchup_score": round(sp.get("matchup_score", 0), 1),
                "strategy_score": round(sp.get("strategy_score", 0), 1),
                "pros": pros, "cons": cons, "verdict": verdict,
                "tier": sp["tier"], "tags": tags,
                "computed_at": datetime.now(UTC).isoformat(),
            })

        # --- Step 9: Push to Supabase ---
        print(f"  Pushing {len(recommendations)} recommendations...")
        db.replace_recommendations(client, recommendations, today)

        # Step 9b: Weekly plan (optimal 7-day assignment)
        try:
            from sync.weekly_plan import build_and_push as build_weekly_plan
            plan = build_weekly_plan(days_ahead=7)
            print(f"  Weekly plan: {len(plan)} days assigned.")
        except Exception as e:
            print(f"  (weekly plan skipped: {e})")

        db.finish_sync_log(client, log_id, players_updated)
        print(f"[{datetime.now():%H:%M}] Sync complete! {len(recommendations)} players scored.")

    except Exception as e:
        traceback.print_exc()
        db.fail_sync_log(client, log_id, str(e))
        print(f"[{datetime.now():%H:%M}] Sync FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_sync()
