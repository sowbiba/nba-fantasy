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
import os
import sys
import time
import traceback
from datetime import UTC, date, datetime, timedelta

import numpy as np

from sync import db
from sync.config import (
    HARD_OUT_STATUSES,
    MIN_MINUTES_L10,
    MINUTES_ADJUSTED_BASE,
    NBA_API_DELAY,
    USE_PAIR_MATCHUP,
    WATCHLIST_BASE,
    WATCHLIST_ELIM_BONUS,
    WATCHLIST_GAME3_SURGE,
    dnp_risk_factor,
    play_probability,
)
from sync.fetcher import (
    fetch_today_scoreboard,
    parse_today_games,
    fetch_live_box_score,
    fetch_player_game_logs_nba_api,
    fetch_team_rosters,
    compute_player_aggregates,
)
from sync.injuries import fetch_all_injuries, match_injury_to_player
from sync.scoring import (
    compute_performance_score,
    league_avg_by_position,
    minutes_adjusted_base,
    position_def_column,
)
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
from sync.personal_strategy import (
    PersonalContext,
    compute_multiplier as compute_personal_multiplier,
)
from sync.ttfl import compute_ttfl_from_game_log
from sync.future import compute_best_future_opportunity


# Watchlist boost constants live in sync.config so main.py and weekly_plan.py
# stay in sync.


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
        # Skip games we've already ingested so the 4-runs-a-day cadence
        # doesn't keep poking NBA for data we already have. A game with at
        # least one row in game_logs has been fetched once and final stats
        # don't change. Step 2b below catches the truly unprocessed
        # matchup_aggregates separately.
        yesterday_games = db.get_today_games(client, yesterday)

        # Pre-fetch all (game_id) rows currently in game_logs and matchup_aggregates
        # so we can skip without per-game round-trips.
        yesterday_final_ids = [
            g["id"] for g in yesterday_games if g["status"] == "final"
        ]
        already_logged_games: set[str] = set()
        already_aggregated_games: set[str] = set()
        if yesterday_final_ids:
            try:
                logged_rows = (
                    client.table("game_logs").select("game_id")
                    .in_("game_id", yesterday_final_ids)
                    .execute().data or []
                )
                already_logged_games = {str(r["game_id"]) for r in logged_rows}
            except Exception as e:
                print(f"  (warn: already-logged-games cache load failed, may re-fetch: {e})")
            try:
                agg_rows = (
                    client.table("matchup_aggregates")
                    .select("processed_game_ids")
                    .execute().data or []
                )
                for r in agg_rows:
                    for gid in r.get("processed_game_ids") or []:
                        already_aggregated_games.add(str(gid))
            except Exception as e:
                print(f"  (warn: already-aggregated-games cache load failed, may re-process: {e})")

        for game in yesterday_games:
            if game["status"] != "final":
                continue
            gid = str(game["id"])

            if gid in already_logged_games:
                print(f"  Box score for {gid} already cached, skipping fetch")
            else:
                print(f"  Fetching box score for {gid}...")
                box_players = fetch_live_box_score(
                    gid,
                    home_tricode=game.get("home_team"),
                    game_date=game.get("date"),
                )
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
                        "fouls": bp.get("fouls", 0),
                        "ttfl_score": bp["ttfl_score"],
                        "is_home": bp["is_home"],
                    })
                if game_logs:
                    db.upsert_game_logs(client, game_logs)

            # Per-pair matchup aggregates: skip if we've already merged
            # this game's data. update_aggregates_for_game is internally
            # idempotent (processed_game_ids check) but the API call still
            # fires before the dedup — we want to skip the call entirely.
            if gid in already_aggregated_games:
                continue
            try:
                from sync.matchups import update_aggregates_for_game
                touched = update_aggregates_for_game(
                    client,
                    game_id=gid,
                    home_team=game["home_team"],
                    away_team=game["away_team"],
                    series_id=game.get("series_id"),
                )
                if touched:
                    print(f"    matchup aggregates: {touched} pair(s) updated")
            except Exception as e:
                print(f"    (matchup aggregates skipped: {e})")

        # Step 2b: update actual_score on picks now that box scores are final.
        # Match on (player_id, game_id) — the game_id is stable whereas the
        # pick date vs game_log date can differ (NBA logs use the finish
        # date in UTC, which is the next calendar day for late West Coast
        # games).
        unscored_picks = client.table("picks").select(
            "id, player_id, game_id, date"
        ).filter("actual_score", "is", "null").execute().data or []
        updated_picks = 0
        # Cache "is the box score for this game actually synced?" lookups so
        # we don't re-query for every pick. A game counts as synced as soon
        # as at least one player row exists in game_logs — that proves the
        # box-score fetch returned something. Without this guard we used to
        # mark picks as DNP (0 pts) whenever fetch_live_box_score happened
        # to return empty (CDN purged + stats API not yet populated, rate
        # limit, transient network failure), which is wrong: the player
        # likely played, we just didn't have the data yet.
        boxscore_synced: dict[str, bool] = {}
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
            # No row for this player. Only treat this as a confirmed DNP if
            # (a) the game is final AND (b) we actually have box-score rows
            # for OTHER players in this game — otherwise the box score
            # simply hasn't been ingested yet and the pick should stay "—".
            game_res = client.table("games").select("status").eq(
                "id", pick["game_id"]
            ).execute()
            if not (game_res.data and game_res.data[0]["status"] == "final"):
                continue
            gid = pick["game_id"]
            if gid not in boxscore_synced:
                any_log = client.table("game_logs").select("player_id").eq(
                    "game_id", gid
                ).limit(1).execute()
                boxscore_synced[gid] = bool(any_log.data)
            if not boxscore_synced[gid]:
                # Box score not yet ingested — leave pick unscored, retry
                # next sync.
                continue
            client.table("picks").update({
                "actual_score": 0
            }).eq("id", pick["id"]).execute()
            updated_picks += 1
        if updated_picks > 0:
            print(f"  Updated {updated_picks} pick(s) with actual score.")

        # --- Step 2b: Catch-up for matchup aggregates ---
        # NBA's BoxScoreMatchupsV3 sometimes returns empty for a game
        # that has just gone final (data isn't published yet) or times
        # out from a rate-limited runner IP. The yesterday-only loop in
        # Step 2 doesn't notice the miss — the game silently never enters
        # processed_game_ids. Each sync rescans the last 14 days for
        # final games we haven't aggregated yet and retries them.
        try:
            from sync.matchups import (
                find_unprocessed_final_games,
                update_aggregates_for_game,
            )
            stragglers = find_unprocessed_final_games(client, days_back=14)
            if stragglers:
                print(f"  Catch-up: {len(stragglers)} unaggregated final game(s)")
                catchup_touched = 0
                catchup_empty = 0
                for g in stragglers:
                    try:
                        touched = update_aggregates_for_game(
                            client,
                            game_id=g["id"],
                            home_team=g["home_team"],
                            away_team=g["away_team"],
                            series_id=g.get("series_id"),
                        )
                    except Exception as e:
                        print(f"    {g['date']} {g['id']}: ERROR ({type(e).__name__})")
                        continue
                    if touched:
                        catchup_touched += touched
                        print(f"    {g['date']} {g['id']}: +{touched} pair rows")
                    else:
                        catchup_empty += 1
                        print(
                            f"    {g['date']} {g['id']}: empty (NBA hasn't "
                            f"published yet, will retry next sync)"
                        )
                print(
                    f"  Catch-up done: {catchup_touched} pair rows added, "
                    f"{catchup_empty} game(s) still empty"
                )
        except Exception as e:
            print(f"  (matchup catch-up skipped: {e})")

        # --- Step 3: Fetch rosters + update players ---
        # Rosters change rarely and a bench-end signing or waiver isn't
        # a TTFL signal we care about. In playoffs they're frozen anyway;
        # in regular season the only events worth catching mid-week are
        # the trade deadline and impactful buyouts, both of which we'll
        # trigger manually with a one-shot sync. Default cadence: weekly.
        ROSTER_REFRESH_INTERVAL_HOURS = 168
        force_rosters = os.environ.get("FORCE_ROSTERS", "").lower() in (
            "1", "true", "yes", "y"
        )
        recent_logs = (
            client.table("sync_log")
            .select("started_at, players_updated, status")
            .eq("status", "success")
            .gt("players_updated", 0)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
            .data
        ) or []
        skip_rosters = False
        if force_rosters:
            print("  FORCE_ROSTERS set, fetching rosters regardless of cache age")
        elif recent_logs:
            last_iso = recent_logs[0]["started_at"]
            try:
                last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                age_h = (datetime.now(UTC) - last_dt).total_seconds() / 3600
                if age_h < ROSTER_REFRESH_INTERVAL_HOURS:
                    skip_rosters = True
                    print(
                        f"  Rosters fresh ({age_h:.1f}h old < "
                        f"{ROSTER_REFRESH_INTERVAL_HOURS}h), skipping fetch"
                    )
            except (ValueError, TypeError):
                pass

        if skip_rosters:
            players_updated = 0
        else:
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
            # Pull a wider window so the L20 still has 20 *played* games
            # after DNPs are filtered out (long injury stretches can leave
            # ~half the recent logs as zeros).
            logs = db.get_player_game_logs(client, pid, limit=40)
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

        # League-average TTFL allowed at each position = the denominator of
        # the matchup factor. It MUST be on the same scale as team_defense's
        # vs_*_ttfl_avg columns (~8-13). Was hardcoded to 40, which silently
        # crushed every perf_score to ~55% (matchup factor ≈0.2 instead of
        # ≈0.8 — e.g. SGA 42→23). Computed live so it tracks the season.
        # The dict also caches team_defense to avoid an N-query loop.
        _all_defense = client.table("team_defense").select("*").execute().data or []
        team_defense_by_team = {r["team"]: r for r in _all_defense}
        league_avg_by_key = league_avg_by_position(_all_defense)

        scored_players = []
        for g in today_games:
            if g["status"] == "final":
                continue
            for p in all_players_db:
                if p["team"] not in (g["home_team"], g["away_team"]):
                    continue
                if p["id"] in picked_ids:
                    continue
                if p.get("injury_status") in HARD_OUT_STATUSES:
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
                opp_defense = team_defense_by_team.get(opponent)

                # Matchup factor = opp's TTFL allowed at this position over the
                # league average at that position (same ~10.5 scale).
                pos_key = position_def_column(p["position"])
                league_avg = league_avg_by_key[pos_key]
                opp_ttfl = (opp_defense.get(pos_key) if opp_defense else None) or league_avg

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

                # Optional pair-matchup signal — gated behind USE_PAIR_MATCHUP.
                # When enabled, the engine looks up `matchup_aggregates` for
                # this (player, opponent) pair in the active series and
                # blends the defender-specific allow rate into matchup_factor
                # at a confidence weight set by accumulated matchup minutes.
                pair_off_per36 = None
                pair_minutes = 0.0
                player_off_per36 = 0.0
                if USE_PAIR_MATCHUP:
                    from sync.matchups import lookup_pair_matchup
                    pair_off_per36, pair_minutes = lookup_pair_matchup(
                        client, p["id"], opponent
                    )
                    # Approximate the player's offensive-only TTFL per 36
                    # from total avg + estimated split (≈70% for guards/
                    # forwards, ≈60% for centers — REB/BLK weight more on
                    # bigs). Good enough; the confidence weight on the
                    # blended factor caps the impact.
                    season_avg = p.get("avg_ttfl_season", 0) or 0
                    avg_min = p.get("avg_minutes_l10", 0) or 24
                    off_share = 0.60 if p["position"] == "C" else 0.70
                    if avg_min > 0:
                        player_off_per36 = (
                            season_avg / avg_min * 36.0 * off_share
                        )

                # Minutes-aware base: recent TTFL/min × expected minutes
                # (DNP-inclusive) so role changes and injuries don't carry
                # stale high-minute games. `logs` already includes DNP rows.
                base = (
                    minutes_adjusted_base(
                        logs, p.get("avg_ttfl_season", 0) or 0, today=date.today()
                    )
                    if MINUTES_ADJUSTED_BASE else None
                )
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
                    pair_allowed_off_ttfl_per36=pair_off_per36,
                    pair_minutes_total=pair_minutes,
                    player_off_avg_per36=player_off_per36,
                    base_override=base,
                )

                scored_players.append({
                    "player": p, "game": g, "perf_score": perf_score,
                    "is_home": is_home, "opponent": opponent,
                    "days_rest": days_rest, "recent_scores": recent_scores,
                    "recent_logs": logs,
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

        # Personal strategy: per-team outlook + per-player save rank. Both
        # tables are optional; when absent the multiplier degrades to 1.0
        # and the engine behaves exactly like before.
        team_outlook_map: dict[str, dict] = {}
        player_rank_map: dict[int, int] = {}
        try:
            to_rows = client.table("team_outlook").select(
                "team, outlook, home_save_top"
            ).execute().data or []
            team_outlook_map = {r["team"]: r for r in to_rows}
            if team_outlook_map:
                print(f"  {len(team_outlook_map)} team outlooks loaded")
        except Exception as e:
            print(f"  (team_outlook table missing, skipping: {e})")
        try:
            pr_rows = client.table("player_team_rank").select(
                "player_id, save_rank"
            ).execute().data or []
            player_rank_map = {r["player_id"]: r["save_rank"] for r in pr_rows}
            if player_rank_map:
                print(f"  {len(player_rank_map)} player save ranks loaded")
        except Exception as e:
            print(f"  (player_team_rank table missing, skipping: {e})")

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
            surge_multiplier = WATCHLIST_GAME3_SURGE if game3_surge else 1.0

            # Injury-aware EV: a Q player with a 55% chance to play has his
            # expected score halved-ish, naturally pushing him below an
            # equivalent clean candidate without a hard exclusion.
            play_prob = play_probability(sp["player"].get("injury_status"))
            # Catches DNP patterns ESPN hasn't flagged yet (status=NULL but
            # 0 min last game). Compounds with play_prob.
            dnp_factor = dnp_risk_factor(sp["recent_logs"])

            # Personal-strategy multiplier — overlays the user's bracket
            # view onto the engine score. Hot streaks and elimination
            # pressure auto-release the save penalty so this never traps
            # the user into ignoring an obvious play.
            team_row = team_outlook_map.get(sp["player"]["team"]) or {}
            personal_ctx = PersonalContext(
                save_rank=player_rank_map.get(pid),
                team_outlook=team_row.get("outlook"),
                home_save_top=bool(team_row.get("home_save_top", True)),
                is_home_game=sp["is_home"],
                elimination_risk=elim,
                avg_l5=sp["player"].get("avg_ttfl_l5", 0) or 0,
                season_avg=sp["player"].get("avg_ttfl_season", 0) or 0,
            )
            personal_mult, personal_reason = compute_personal_multiplier(personal_ctx)

            sp["strategy_score"] = strategy_score
            sp["reservation_penalty"] = reservation
            sp["watchlist_priority"] = priority
            sp["watchlist_boost"] = watchlist_boost
            sp["game3_surge"] = game3_surge
            sp["play_probability"] = play_prob
            sp["dnp_risk_factor"] = dnp_factor
            sp["personal_multiplier"] = personal_mult
            sp["personal_reason"] = personal_reason
            sp["save_rank"] = personal_ctx.save_rank
            sp["team_outlook"] = personal_ctx.team_outlook
            # Honest projection — this is what we display and compare against
            # the actual score. It deliberately excludes the watchlist boost
            # and the G3 surge: those are user-preference nudges, not forecasts
            # of TTFL output (a starred player doesn't score more, you just
            # prefer to play him).
            sp["estimated_score"] = (
                strategy_score
                * (1.0 - reservation)
                * play_prob
                * dnp_factor
                * personal_mult
            )
            # Ranking score — drives the reco ordering (and therefore `rank`)
            # so a starred must-play wins close calls. Not stored: its effect
            # is the rank itself; estimated_score above stays honest.
            sp["rank_score"] = (
                sp["estimated_score"] * (1.0 + watchlist_boost) * surge_multiplier
            )
            sp["series_score"] = series_score
            sp["game_number"] = game.get("game_number", 0) or 0
            sp["elimination"] = elim
            sp["player_series_is_home"] = player_series_is_home

        scored_players.sort(key=lambda x: x["rank_score"], reverse=True)
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
                "dnp_risk_factor": sp.get("dnp_risk_factor", 1.0),
                "recent_minutes": [
                    (log.get("minutes") or 0) for log in sp.get("recent_logs", [])[:3]
                ],
                "personal_multiplier": sp.get("personal_multiplier", 1.0),
                "personal_reason": sp.get("personal_reason", ""),
                "save_rank": sp.get("save_rank"),
                "team_outlook": sp.get("team_outlook"),
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
            if sp.get("dnp_risk_factor", 1.0) < 1.0:
                tags.append("dnp_risk")
            personal_reason = sp.get("personal_reason") or ""
            if personal_reason and personal_reason not in ("no_outlook", "no_rank"):
                tags.append(personal_reason)
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
