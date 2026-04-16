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
from datetime import date, datetime, timedelta
from typing import Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

from sync import db
from sync.scoring import compute_performance_score
from sync.strategy import elimination_risk


LEAGUE_AVG_TTFL = 40

# Reservation penalty: maximum score reduction for elites of deep-run
# contenders in early rounds. This forces the Hungarian algorithm to
# *save* these players for conference finals / finals unless the only
# alternative is tragically bad.
MAX_RESERVATION_PENALTY = 0.60  # up to -60% on projected score

# Round factor: how much reservation applies per round. Early = full force,
# finals = no reservation (use everyone).
ROUND_RESERVATION_FACTOR = {1: 1.0, 2: 0.55, 3: 0.2, 4: 0.0}

# Team potential by playoff seeding. Home court in a Round 1 series = top
# seed (1-4) = high probability of advancing to Round 2+. Away team in R1
# (seed 5-8) = lower probability but still alive. Play-in survivor = lowest.
TEAM_POTENTIAL_TOP_SEED = 1.0
TEAM_POTENTIAL_LOW_SEED = 0.5
TEAM_POTENTIAL_UNKNOWN = 0.3


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


def compute_team_potential_scores(active_series: list[dict]) -> dict[str, float]:
    """Translate playoff seeding into a team-potential proxy.

    Team is the home team (higher seed, home court advantage) in a R1
    series → top-seed potential, probably advances to R2.
    Team is the away team (seed 5-8) → still alive but more likely to lose.
    Team not yet in a series (play-in winner TBD) → lowest potential.

    This replaces the previous top-5-avg approach which was biased against
    teams with a superstar + weak supporting cast (e.g., DEN with Jokic).
    """
    scores: dict[str, float] = {}
    for s in active_series:
        if s.get("round") == 1:
            scores[s["home_team"]] = TEAM_POTENTIAL_TOP_SEED
            scores[s["away_team"]] = TEAM_POTENTIAL_LOW_SEED
        elif s.get("round", 1) >= 2:
            scores[s["home_team"]] = TEAM_POTENTIAL_TOP_SEED
            scores[s["away_team"]] = TEAM_POTENTIAL_TOP_SEED
    return scores


def compute_reservation_penalty(
    player_season_avg: float,
    team_potential: float,
    round_num: int,
) -> float:
    """Fraction of the player's score to dock as "reservation tax".

    A top-shelf player (avg_season 55, e.g. Jokic) on a top-seed team
    (potential 1.0) in Round 1 gets the full MAX_RESERVATION_PENALTY so
    the Hungarian algorithm avoids burning him on Game 2 when better spots
    await in Rounds 2-4. A solid player (avg_season 32) on a play-in team
    barely gets any penalty.
    """
    if player_season_avg <= 32:
        return 0.0  # not elite, no reservation needed
    # Elite factor 0..1 (player's own level). 32→0, 55→1.
    elite_factor = min(1.0, (player_season_avg - 32) / 23)
    round_factor = ROUND_RESERVATION_FACTOR.get(round_num, 0.0)
    raw = elite_factor * team_potential * round_factor
    return min(MAX_RESERVATION_PENALTY, raw * MAX_RESERVATION_PENALTY)


def _opponent_ttfl(team_defense: dict[str, dict], opponent: str, position: str) -> float:
    td = team_defense.get(opponent)
    if not td:
        return LEAGUE_AVG_TTFL
    if position == "G":
        v = td.get("vs_guards_ttfl_avg") or 0
    elif position == "F":
        v = td.get("vs_forwards_ttfl_avg") or 0
    else:
        v = td.get("vs_centers_ttfl_avg") or 0
    return v or LEAGUE_AVG_TTFL


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

    # Team defense cache
    td_rows = client.table("team_defense").select("*").execute().data
    team_defense = {r["team"]: r for r in td_rows}

    # Active series for elimination detection
    active_series = db.get_active_series(client)

    # Team potential by seeding → reservation factor per team
    team_potential = compute_team_potential_scores(active_series)

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
                if p.get("injury_status") in ("Out", "Doubtful"):
                    continue
                season_avg = p.get("avg_ttfl_season", 0) or 0
                # Filter very-low-usage players to keep the matrix tractable
                if season_avg < 10:
                    continue

                # Get recent scores (cached)
                if p["id"] not in recent_by_player:
                    logs = (
                        client.table("game_logs").select("ttfl_score")
                        .eq("player_id", p["id"])
                        .order("date", desc=True).limit(10).execute().data
                    )
                    recent_by_player[p["id"]] = [l["ttfl_score"] for l in logs]
                recent_scores = recent_by_player[p["id"]]

                # Days rest approximated from the gap between today and the game
                try:
                    game_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                    days_rest = max(1, (game_dt - today).days)
                except (ValueError, TypeError):
                    days_rest = 2

                opp_ttfl = _opponent_ttfl(team_defense, opponent, p["position"])

                perf = compute_performance_score(
                    avg_l5=p.get("avg_ttfl_l5", 0) or 0,
                    avg_l10=p.get("avg_ttfl_l10", 0) or 0,
                    avg_l20=p.get("avg_ttfl_l20", 0) or 0,
                    opponent_ttfl_at_position=opp_ttfl,
                    league_avg_ttfl_at_position=LEAGUE_AVG_TTFL,
                    home_avg=p.get("home_avg", 0) or 0,
                    away_avg=p.get("away_avg", 0) or 0,
                    season_avg=season_avg,
                    is_home=is_home,
                    days_rest=days_rest,
                    recent_scores=recent_scores,
                    stddev=p.get("stddev_ttfl", 0) or 0,
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

                # Reservation tax: discourage burning elites of deep contenders
                # in early rounds. Elimination risk overrides this entirely.
                reservation = 0.0
                if elim != "critical":
                    round_num = series["round"] if series else 1
                    tp = team_potential.get(team, TEAM_POTENTIAL_UNKNOWN)
                    reservation = compute_reservation_penalty(
                        player_season_avg=season_avg,
                        team_potential=tp,
                        round_num=round_num,
                    )
                final_score = perf * (1.0 - reservation)

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
        generated_at = datetime.utcnow()

    # Wipe and re-insert (small table, no FK constraints)
    client.table("weekly_plan").delete().neq("id", 0).execute()
    if not plan:
        return

    rows = []
    for cand in plan:
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
