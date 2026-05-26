"""Build an optimal 7-day pick plan using the Hungarian algorithm.

Problem statement:
  - We have N upcoming game days in a rolling window (configurable).
  - On each day, a set of players is eligible (their team plays, they're
    not already picked for the playoffs cycle, and they are not OUT/Doubtful).
  - For each (day, player) pair we can compute an estimated TTFL score
    using the same 6-factor engine used for "tonight".
  - Constraint: each player can only be used at most once across the window.

Goal: maximize total estimated score over the window by assigning exactly
one player per day.

This is a classic assignment problem. We use scipy's
`linear_sum_assignment` which implements the Hungarian algorithm (O(n^3)).

The output is a list of (date, player_id, estimated_score, reasoning) that
is pushed to the `weekly_plan` table.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

from sync import db
from sync.advisor import generate_plan_argumentaire, generate_plan_verdict
from sync.config import (
    HARD_OUT_STATUSES,
    MIN_MINUTES_L10,
    USE_PAIR_MATCHUP,
    WATCHLIST_BASE,
    WATCHLIST_ELIM_BONUS,
    WATCHLIST_GAME3_SURGE,
    dnp_risk_factor,
    play_probability,
    save_tax_for_game,
)
from sync.personal_strategy import (
    PersonalContext,
    compute_multiplier as compute_personal_multiplier,
)
from sync.scoring import (
    compute_performance_score,
    league_avg_by_position,
    position_def_column,
)
from sync.strategy import (
    K_VAR,
    LAMBDA_RISK,
    TEAM_POTENTIAL_UNKNOWN,
    TIER_CAPITAL_VALUE,
    compute_opportunity_cost_fraction,
    compute_team_potential_scores,
    elimination_risk,
    expected_remaining_player_games,
    prob_game_played,
    prob_team_advances,
    prob_team_eliminated_this_round,
    team_single_game_win_prob,
    tier_demand_factor,
)


@dataclass
class Candidate:
    """One (player, day) scoring cell in the assignment matrix."""
    player_id: int
    player_name: str
    team: str
    position: str
    date: str
    game_id: str
    opponent: str
    is_home: bool
    estimated_score: float
    game_number: int | None = None
    series_score: tuple[int, int] = (0, 0)
    elimination: str = "none"
    raw_perf_score: float = 0.0  # before reservation tax
    reservation_penalty: float = 0.0  # fraction 0..MAX_RESERVATION_PENALTY
    # Stats carried through for argumentaire generation in push_plan
    avg_l5: float = 0.0
    avg_season: float = 0.0
    stddev: float = 0.0
    home_avg: float = 0.0
    away_avg: float = 0.0
    ceiling: float = 0.0
    floor: float = 0.0
    opp_ttfl_at_position: float = 0.0
    league_avg_at_position: float = 10.5  # matchup denominator actually used
    watchlist_priority: int | None = None
    game3_surge: bool = False
    # Probabilistic engine fields
    pick_probability: float = 1.0           # P(this game actually happens)
    p_team_eliminated: float = 0.0          # P(player's team eliminated this round)
    p_team_advances: float = 1.0            # complement, kept for reasoning
    expected_remaining_after: float = 0.0   # E[games player still has after this slot]
    waste_cost: float = 0.0                 # absolute cost units (for verdict)
    tier_alternatives_at_risk: list[str] | None = None  # other watchlist names at risk
    # Injury-aware EV: P(player actually plays given his current status).
    # 1.0 for clean rotation players, 0.55 for Questionable, etc.
    play_probability: float = 1.0
    injury_status: str | None = None


def _fr_day_label(iso_date: str) -> str:
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except ValueError:
        return iso_date
    fr_days = {
        0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi",
        4: "Vendredi", 5: "Samedi", 6: "Dimanche",
    }
    return f"{fr_days[d.weekday()]} {d.day}"


def _opponent_ttfl(
    team_defense: dict[str, dict],
    opponent: str,
    position: str,
    league_avg_by_key: dict[str, float],
) -> float:
    col = position_def_column(position)
    fallback = league_avg_by_key[col]  # same-scale neutral when data missing
    td = team_defense.get(opponent)
    if not td:
        return fallback
    return (td.get(col) or 0) or fallback


def build_candidates(
    client,
    today: date,
    days_ahead: int = 7,
    mode: str = "playoffs",
) -> tuple[list[Candidate], list[str]]:
    """Enumerate all viable (day, player) candidates over the next N days.

    Returns (candidates, sorted_days). `sorted_days` is the list of unique
    dates (ISO string) that have at least one game — this is the Y-axis of
    the assignment matrix.
    """
    start_iso = today.isoformat()
    end_iso = (today + timedelta(days=days_ahead)).isoformat()

    games = (
        client.table("games").select("*")
        .gte("date", start_iso).lte("date", end_iso)
        .order("date").execute().data
    )
    # Skip games with TBD teams (play-in winner pending) and finished games
    games = [
        g for g in games
        if g.get("home_team") not in (None, "TBD", "")
        and g.get("away_team") not in (None, "TBD", "")
        and g.get("status") != "final"
    ]

    all_players = client.table("players").select("*").execute().data

    # Already picked players (excluded from plan)
    picked = db.get_picked_player_ids(client, mode=mode)

    # Team defense cache + dynamic per-position league means (matchup denom)
    td_rows = client.table("team_defense").select("*").execute().data
    team_defense = {r["team"]: r for r in td_rows}
    league_avg_by_key = league_avg_by_position(td_rows)

    # Active series for elimination detection
    active_series = db.get_active_series(client)

    # User series forecasts (optional)
    forecast_map: dict[int, dict] = {}
    try:
        fc_rows = client.table("series_forecast").select(
            "series_id, winner_team, expected_games"
        ).execute().data or []
        forecast_map = {r["series_id"]: r for r in fc_rows}
    except Exception:
        pass

    # Team potential by seeding (blended with user forecasts)
    team_potential = compute_team_potential_scores(
        active_series, forecasts=forecast_map
    )

    # User watchlist (optional, table may not exist yet)
    watchlist_map: dict[int, int] = {}
    try:
        wl_rows = client.table("player_watchlist").select(
            "player_id, priority"
        ).execute().data or []
        watchlist_map = {r["player_id"]: r["priority"] for r in wl_rows}
    except Exception:
        pass

    # Personal-strategy layer: per-team outlook + per-player save rank.
    # Optional; the plan still runs if the tables are missing.
    team_outlook_map: dict[str, dict] = {}
    player_rank_map: dict[int, int] = {}
    try:
        to_rows = client.table("team_outlook").select(
            "team, outlook, home_save_top"
        ).execute().data or []
        team_outlook_map = {r["team"]: r for r in to_rows}
    except Exception:
        pass
    try:
        pr_rows = client.table("player_team_rank").select(
            "player_id, save_rank"
        ).execute().data or []
        player_rank_map = {r["player_id"]: r["save_rank"] for r in pr_rows}
    except Exception:
        pass

    # Eligible pool = union of watchlist and ranked players. The plan must
    # allocate the user's finite, deliberately-chosen capital, not roam
    # across the whole roster.
    eligible_pool = set(watchlist_map.keys()) | set(player_rank_map.keys())

    # Remaining (not-yet-picked) watchlist counts per tier — drives the
    # tier_demand_factor for opportunity cost.
    picked_set = set(picked)
    remaining_by_tier = {1: 0, 2: 0, 3: 0}
    for pid, pr in watchlist_map.items():
        if pid in picked_set:
            continue
        if pr in remaining_by_tier:
            remaining_by_tier[pr] += 1
    expected_picks_left = max(1, len(games))  # rough proxy: candidate game days

    # Per-team ranking of available (non-cramed) players by season avg.
    # Used by save_tax_for_game to identify which specific ranks
    # (TEAM_SAVE_RANKS) to protect against Hungarian-greedy burn.
    # Computed once per sync — the picked set doesn't change mid-window.
    team_rank_map: dict[int, int] = {}
    for t in {p["team"] for p in all_players}:
        teammates_available = sorted(
            (
                pp for pp in all_players
                if pp["team"] == t
                and pp["id"] not in picked
                and (pp.get("avg_ttfl_season") or 0) > 0
            ),
            key=lambda x: -(x.get("avg_ttfl_season") or 0),
        )
        for rank, pp in enumerate(teammates_available):
            team_rank_map[pp["id"]] = rank

    # Per-team single-game win prob & expected remaining player games. Cached
    # per team so we don't hit Markov for every (player, day) combo.
    team_p_win: dict[str, float] = {}
    team_remaining_games: dict[str, float] = {}
    team_eliminated_this_round: dict[str, float] = {}
    team_advances: dict[str, float] = {}
    series_by_team: dict[str, dict] = {}
    for s in active_series:
        if s.get("status") != "active":
            continue
        fc = forecast_map.get(s.get("id"))
        for team_field, is_home_team in (("home_team", True), ("away_team", False)):
            team = s.get(team_field)
            if not team:
                continue
            p_team = team_single_game_win_prob(team, s, fc)
            team_p_win[team] = p_team
            series_by_team[team] = s
            state = (s.get("home_wins") or 0, s.get("away_wins") or 0)
            team_eliminated_this_round[team] = prob_team_eliminated_this_round(
                state, p_team, is_home_team
            )
            team_advances[team] = prob_team_advances(
                state, p_team, is_home_team
            )
            current_round = s.get("round") or 1
            team_remaining_games[team] = expected_remaining_player_games(
                team, s, current_round, forecast_map
            )

    # Watchlist players whose team has high elimination risk this round.
    # Used by the verdict to surface "if X loses tonight you also lose Y".
    name_by_pid: dict[int, str] = {p["id"]: p["name"] for p in all_players}
    at_risk_by_team: dict[str, list[str]] = {}
    for pid, pr in watchlist_map.items():
        if pid in picked_set:
            continue
        player_row = next((p for p in all_players if p["id"] == pid), None)
        if not player_row:
            continue
        t = player_row["team"]
        risk = team_eliminated_this_round.get(t, 0.0)
        if risk >= 0.35:
            at_risk_by_team.setdefault(t, []).append(player_row["name"])

    # Recent game log cache per player (for trend factor)
    # Bulk fetch by paging game_logs and indexing
    recent_by_player: dict[int, list[int]] = {}

    candidates: list[Candidate] = []
    dates_with_games: set[str] = set()

    for g in games:
        date_str = g["date"]
        dates_with_games.add(date_str)

        # Find the series that matches this game
        series = next(
            (
                s for s in active_series
                if {s["home_team"], s["away_team"]} == {g["home_team"], g["away_team"]}
            ),
            None,
        )
        series_score = (
            (series["home_wins"], series["away_wins"]) if series else (0, 0)
        )

        for team_field, is_home in (("home_team", True), ("away_team", False)):
            team = g[team_field]
            opponent = g["away_team"] if is_home else g["home_team"]

            for p in all_players:
                if p["team"] != team:
                    continue
                if p["id"] in picked:
                    continue
                # Eligibility: watchlist OR per-team save rank. Players
                # outside both are deep-bench candidates the user has not
                # signed up for.
                if p["id"] not in eligible_pool:
                    continue
                if p.get("injury_status") in HARD_OUT_STATUSES:
                    continue
                season_avg = p.get("avg_ttfl_season", 0) or 0
                # Filter very-low-usage players to keep the matrix tractable
                if season_avg < 10:
                    continue
                # Minutes gate: rotation-fringe players whose L10 minutes are
                # below threshold have aggregates dominated by DNPs or
                # garbage-time outliers. Drop them outright. Skip the gate
                # when avg_minutes_l10 is still at its 0 default — that
                # means the column hasn't been backfilled yet, and we'd
                # rather fall back to the season_avg filter than exclude
                # everyone.
                avg_min = p.get("avg_minutes_l10", 0) or 0
                if avg_min > 0 and avg_min < MIN_MINUTES_L10:
                    continue

                # Get recent scores + minutes (cached). Minutes feed
                # dnp_risk_factor; ttfl_score feeds the trend factor.
                if p["id"] not in recent_by_player:
                    logs = (
                        client.table("game_logs").select("ttfl_score, minutes")
                        .eq("player_id", p["id"])
                        .order("date", desc=True).limit(10).execute().data
                    )
                    recent_by_player[p["id"]] = logs
                recent_logs = recent_by_player[p["id"]]
                recent_scores = [l["ttfl_score"] for l in recent_logs]

                # Days rest approximated from the gap between today and the game
                try:
                    game_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                    days_rest = max(1, (game_dt - today).days)
                except (ValueError, TypeError):
                    days_rest = 2

                opp_ttfl = _opponent_ttfl(
                    team_defense, opponent, p["position"], league_avg_by_key
                )
                league_avg_pos = league_avg_by_key[position_def_column(p["position"])]

                pair_off_per36 = None
                pair_minutes = 0.0
                player_off_per36 = 0.0
                if USE_PAIR_MATCHUP:
                    from sync.matchups import lookup_pair_matchup
                    pair_off_per36, pair_minutes = lookup_pair_matchup(
                        client, p["id"], opponent
                    )
                    avg_min = p.get("avg_minutes_l10", 0) or 24
                    off_share = 0.60 if p["position"] == "C" else 0.70
                    if avg_min > 0:
                        player_off_per36 = season_avg / avg_min * 36.0 * off_share

                perf = compute_performance_score(
                    avg_l5=p.get("avg_ttfl_l5", 0) or 0,
                    avg_l10=p.get("avg_ttfl_l10", 0) or 0,
                    avg_l20=p.get("avg_ttfl_l20", 0) or 0,
                    opponent_ttfl_at_position=opp_ttfl,
                    league_avg_ttfl_at_position=league_avg_pos,
                    home_avg=p.get("home_avg", 0) or 0,
                    away_avg=p.get("away_avg", 0) or 0,
                    season_avg=season_avg,
                    is_home=is_home,
                    days_rest=days_rest,
                    recent_scores=recent_scores,
                    stddev=p.get("stddev_ttfl", 0) or 0,
                    pair_allowed_off_ttfl_per36=pair_off_per36,
                    pair_minutes_total=pair_minutes,
                    player_off_avg_per36=player_off_per36,
                )

                # Elimination risk for this specific game's series
                player_series_is_home = bool(
                    series and team == series["home_team"]
                )
                elim = elimination_risk(series_score, player_series_is_home) if series else "none"
                # Modest boost so elimination-risk candidates rise in the plan
                if elim == "critical":
                    perf *= 1.15
                elif elim == "high":
                    perf *= 1.05

                # Variance-adjusted utility: pénalise les profils volatils
                # (high stddev) en gardant intactes les sanity-stable elites.
                stddev_v = p.get("stddev_ttfl", 0) or 0
                expected_utility = max(1.0, perf - K_VAR * stddev_v)

                # Probabilité que ce match précis ait lieu, depuis l'état
                # actuel de la série (Markov). 1.0 si match déjà programmé
                # comme le tout prochain (déjà-played + 1).
                pick_prob = 1.0
                p_team_elim = 0.0
                p_team_adv = 1.0
                expected_remaining = 0.0
                if series and g.get("game_number"):
                    state = (
                        series.get("home_wins") or 0,
                        series.get("away_wins") or 0,
                    )
                    p_home_series = team_p_win.get(series["home_team"], 0.5)
                    pick_prob = prob_game_played(
                        state, g["game_number"], p_home_series
                    )
                    p_team_elim = team_eliminated_this_round.get(team, 0.0)
                    p_team_adv = team_advances.get(team, 1.0)
                    expected_remaining = max(
                        0.0, team_remaining_games.get(team, 0.0) - pick_prob
                    )

                # Coût d'opportunité probabiliste : retarde les picks "safe"
                # qui ont beaucoup de matchs devant eux. Élimination critique
                # désactive l'opp_cost (le pick devient obligatoire ce soir).
                priority = watchlist_map.get(p["id"])
                if elim == "critical":
                    reservation = 0.0
                else:
                    demand = tier_demand_factor(
                        priority,
                        remaining_by_tier.get(priority, 0) if priority else 0,
                        expected_picks_left,
                    )
                    reservation = compute_opportunity_cost_fraction(
                        expected_utility=expected_utility,
                        expected_remaining_after=expected_remaining,
                        tier_demand_factor=demand,
                    )

                # Watchlist boost (same model as daily reco) + challenger
                # Game 3 surge for flagged players only.
                base_boost = WATCHLIST_BASE.get(priority, 0) if priority else 0
                elim_boost = (
                    WATCHLIST_ELIM_BONUS.get(elim, 0) if priority else 0
                )
                watchlist_boost = base_boost + elim_boost

                player_wins = (
                    series_score[0] if player_series_is_home else series_score[1]
                )
                opponent_wins = (
                    series_score[1] if player_series_is_home else series_score[0]
                )
                game3_surge = bool(
                    priority
                    and is_home
                    and g.get("game_number") == 3
                    and player_wins == 0
                    and opponent_wins == 2
                )
                surge_multiplier = WATCHLIST_GAME3_SURGE if game3_surge else 1.0

                # Loss-aversion penalty: si le match a une bonne chance de
                # ne pas avoir lieu, déduire une perte attendue pondérée par
                # la valeur du tier (★★★ pèse plus qu'un ★).
                tier_value = TIER_CAPITAL_VALUE.get(priority, 0.0) if priority else 0.0
                waste_cost_value = (1.0 - pick_prob) * tier_value

                # Injury-aware EV (Q/DTD/Probable get downweighted; OUT/
                # Doubtful are filtered above). Stacks multiplicatively with
                # pick_prob: a Q player on a maybe-played G7 takes both hits.
                play_prob = play_probability(p.get("injury_status"))
                # Recent-DNP penalty for cases ESPN's flag hasn't caught up.
                dnp_factor = dnp_risk_factor(recent_logs)

                # Personal-strategy multiplier — the same overlay used for
                # the daily reco. Spreads the user's bracket view across
                # the multi-day plan: rank-1 OKC players naturally drift
                # towards later days while LAL ranks fill earlier days.
                team_row = team_outlook_map.get(team) or {}
                personal_ctx = PersonalContext(
                    save_rank=player_rank_map.get(p["id"]),
                    team_outlook=team_row.get("outlook"),
                    home_save_top=bool(team_row.get("home_save_top", True)),
                    is_home_game=is_home,
                    elimination_risk=elim,
                    avg_l5=p.get("avg_ttfl_l5", 0) or 0,
                    season_avg=season_avg,
                )
                personal_mult, _personal_reason = compute_personal_multiplier(
                    personal_ctx
                )

                # Team save tax: penalize top-N players of thin-pool teams
                # so the Hungarian solver defers them to late-series spots
                # (G6/G7) or releases them on critical elimination. The
                # decay across game_number 2→6 means the engine naturally
                # spreads "burns" of mid-tier players first while keeping
                # ★ candidates available for must-win contexts.
                player_team_rank = team_rank_map.get(p["id"], 999)
                save_tax = save_tax_for_game(
                    team, player_team_rank, g.get("game_number"), elim
                )

                final_score = (
                    expected_utility
                    * (1.0 - reservation)
                    * (1.0 + watchlist_boost)
                    * surge_multiplier
                    * pick_prob
                    * play_prob
                    * dnp_factor
                    * personal_mult
                    * (1.0 - save_tax)
                    - LAMBDA_RISK * waste_cost_value
                )
                # Don't let the assignment matrix see a negative cell — the
                # Hungarian sentinel is a HUGE positive cost; negative final
                # scores would still be picked but inflate weirdly.
                final_score = max(0.0, final_score)

                recent_ceiling = max(recent_scores) if recent_scores else 0
                recent_floor = min(recent_scores) if recent_scores else 0

                # Other watchlist players also at elimination risk if this
                # team's series goes the wrong way tonight — referenced by
                # the verdict for "you also lose Y" framing.
                alts_at_risk = [
                    name for name in at_risk_by_team.get(team, [])
                    if name != p["name"]
                ][:3]

                candidates.append(Candidate(
                    player_id=p["id"],
                    player_name=p["name"],
                    team=team,
                    position=p["position"],
                    date=date_str,
                    game_id=g["id"],
                    opponent=opponent,
                    is_home=is_home,
                    estimated_score=float(final_score),
                    raw_perf_score=float(perf),
                    reservation_penalty=reservation,
                    game_number=g.get("game_number"),
                    series_score=series_score,
                    elimination=elim,
                    avg_l5=float(p.get("avg_ttfl_l5", 0) or 0),
                    avg_season=float(season_avg),
                    stddev=float(p.get("stddev_ttfl", 0) or 0),
                    home_avg=float(p.get("home_avg", 0) or 0),
                    away_avg=float(p.get("away_avg", 0) or 0),
                    ceiling=float(recent_ceiling),
                    floor=float(recent_floor),
                    opp_ttfl_at_position=float(opp_ttfl),
                    league_avg_at_position=float(league_avg_pos),
                    watchlist_priority=priority,
                    game3_surge=game3_surge,
                    pick_probability=float(pick_prob),
                    p_team_eliminated=float(p_team_elim),
                    p_team_advances=float(p_team_adv),
                    expected_remaining_after=float(expected_remaining),
                    waste_cost=float(waste_cost_value),
                    tier_alternatives_at_risk=alts_at_risk,
                    play_probability=float(play_prob),
                    injury_status=p.get("injury_status"),
                ))

    return candidates, sorted(dates_with_games)


def optimize_plan(
    candidates: list[Candidate], days: list[str]
) -> list[Candidate]:
    """Solve the assignment problem. Returns one Candidate per day (the plan)."""
    if not candidates or not days:
        return []

    # Build mapping: players (rows index), days (cols index)
    player_ids = sorted({c.player_id for c in candidates})
    pid_to_row = {pid: i for i, pid in enumerate(player_ids)}
    day_to_col = {d: i for i, d in enumerate(days)}

    # Cost matrix: rows = players, cols = days. Cost = -score (we maximize).
    # Unassignable cells (player doesn't play that day) get a huge cost so
    # they're never preferred. Use a sentinel well above any real score.
    n_players = len(player_ids)
    n_days = len(days)
    HUGE = 1e6
    cost = np.full((n_players, n_days), HUGE, dtype=float)

    # For each (player, day) we may have multiple candidates (home and away
    # can't both happen, but defensive). Keep the best.
    best_cand: dict[tuple[int, str], Candidate] = {}
    for c in candidates:
        key = (c.player_id, c.date)
        if key not in best_cand or c.estimated_score > best_cand[key].estimated_score:
            best_cand[key] = c

    for (pid, d), c in best_cand.items():
        cost[pid_to_row[pid], day_to_col[d]] = -c.estimated_score

    # linear_sum_assignment works on rectangular matrices. Since n_players
    # >> n_days usually, it returns n_days assignments (one per column in
    # the input row_ind, col_ind pairs).
    row_ind, col_ind = linear_sum_assignment(cost)

    plan_by_day: dict[str, Candidate] = {}
    for r, c_idx in zip(row_ind, col_ind):
        # Skip cells that were sentinels
        if cost[r, c_idx] >= HUGE:
            continue
        d = days[c_idx]
        pid = player_ids[r]
        cand = best_cand.get((pid, d))
        if cand:
            plan_by_day[d] = cand

    # Return plan in chronological order
    return [plan_by_day[d] for d in days if d in plan_by_day]


def generate_reasoning(cand: Candidate) -> str:
    """Short one-liner explaining why this player was chosen for this day."""
    parts: list[str] = []
    if cand.elimination == "critical":
        parts.append("⚠ équipe en élimination")
    if cand.is_home:
        parts.append("🏠 domicile")
    else:
        parts.append("✈ extérieur")
    if cand.game_number:
        parts.append(f"Game {cand.game_number}")
    hw, aw = cand.series_score
    if hw + aw > 0:
        parts.append(f"série {hw}-{aw}")
    if cand.reservation_penalty > 0.1:
        pct = round(cand.reservation_penalty * 100)
        parts.append(f"pick rare malgré réservation -{pct}%")
    return " · ".join(parts)


def push_plan(client, plan: list[Candidate], generated_at: datetime | None = None):
    """Replace the weekly_plan rows in the database."""
    if generated_at is None:
        generated_at = datetime.now(UTC)

    # Wipe and re-insert (small table, no FK constraints)
    client.table("weekly_plan").delete().neq("id", 0).execute()
    if not plan:
        return

    # Drop low-confidence tail picks: when pick_probability < 0.4, the
    # discounted score is essentially noise (a G7 at 0.4 prob with a fragile
    # roster slot ends up below 3 pts) and would mislead more than help.
    # The next sync will populate these days as series outcomes resolve.
    PICK_PROB_FLOOR = 0.4

    rows = []
    for cand in plan:
        if cand.pick_probability < PICK_PROB_FLOOR:
            continue
        ctx = {
            "avg_l5": cand.avg_l5,
            "avg_season": cand.avg_season,
            "stddev": cand.stddev,
            "home_avg": cand.home_avg,
            "away_avg": cand.away_avg,
            "ceiling": cand.ceiling,
            "floor": cand.floor,
            "opp_ttfl_at_position": cand.opp_ttfl_at_position,
            "league_avg_ttfl": cand.league_avg_at_position,
            "opponent": cand.opponent,
            "position": cand.position,
            "is_home": cand.is_home,
            "game_number": cand.game_number,
            "series_score": cand.series_score,
            "elimination": cand.elimination,
            "reservation_penalty": cand.reservation_penalty,
            "watchlist_priority": cand.watchlist_priority,
            "game3_surge": cand.game3_surge,
            "estimated_score": cand.estimated_score,
            "day_label": _fr_day_label(cand.date),
            "team": cand.team,
            "player_name": cand.player_name,
            # Probabilistic context for the conditional verdict
            "pick_probability": cand.pick_probability,
            "p_team_eliminated": cand.p_team_eliminated,
            "p_team_advances": cand.p_team_advances,
            "expected_remaining_after": cand.expected_remaining_after,
            "waste_cost": cand.waste_cost,
            "tier_alternatives_at_risk": cand.tier_alternatives_at_risk or [],
        }
        pros, cons = generate_plan_argumentaire(ctx)
        verdict = generate_plan_verdict(ctx)
        rows.append({
            "date": cand.date,
            "player_id": cand.player_id,
            "game_id": cand.game_id,
            "estimated_score": round(cand.estimated_score, 1),
            "tier": None,  # can enrich later
            "is_home": cand.is_home,
            "opponent": cand.opponent,
            "game_number": cand.game_number,
            "elimination": cand.elimination,
            "reasoning": generate_reasoning(cand),
            "pros": pros,
            "cons": cons,
            "verdict": verdict,
            "pick_probability": round(cand.pick_probability, 3),
            "generated_at": generated_at.isoformat(),
        })
    client.table("weekly_plan").insert(rows).execute()


def build_and_push(days_ahead: int = 7) -> list[Candidate]:
    """Entry point called from cron."""
    client = db.get_client()
    today = date.today()
    candidates, days = build_candidates(client, today, days_ahead=days_ahead)
    plan = optimize_plan(candidates, days)
    push_plan(client, plan)
    return plan


if __name__ == "__main__":
    import sys
    plan = build_and_push(days_ahead=7)
    print(f"Plan sur {len(plan)} jours :")
    for cand in plan:
        print(
            f"  {_fr_day_label(cand.date)} · {cand.player_name} ({cand.team} "
            f"{'vs' if cand.is_home else '@'} {cand.opponent}) "
            f"→ {cand.estimated_score:.1f}"
        )
