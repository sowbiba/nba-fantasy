import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ESPN injury endpoint template
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# NBA API request delay (avoid rate limiting). 0.6s was burning Akamai
# credit on roster bursts (30 calls in 18s). NBA stats has no public
# rate-limit documentation; community wisdom converges on ~5-10s
# between stats.nba.com calls. 5s is the lower bound of that range and
# keeps us ~30× under typical Cloudflare burst thresholds. The slowest
# sync path (full roster refresh, 30 calls) is ~150s = 2.5min, run
# only every 72h.
NBA_API_DELAY = 5.0  # seconds between requests

# Scoring weights
WEIGHTS = {
    "weighted_avg": 0.35,
    "matchup": 0.25,
    "home_away": 0.10,
    "fatigue": 0.10,
    "trend": 0.10,
    "consistency": 0.10,
}

# Fatigue modifiers
FATIGUE = {
    "b2b": -0.08,
    "3_in_4": -0.12,
    "rest_3plus": 0.03,
}

# Probability that a player with a given ESPN injury_status will actually
# suit up. Values come from rough historical observation (see TTFL post-
# mortem on Q/DTD picks). Anything not in the map is treated as available
# (probability 1.0).
INJURY_PLAY_PROBABILITY = {
    "Out": 0.00,
    "Out For Season": 0.00,
    "Suspended": 0.00,
    "Doubtful": 0.20,
    "Questionable": 0.55,
    "Day-To-Day": 0.65,
    "Game-Time Decision": 0.55,
    "Probable": 0.85,
}

# Hard exclusion: players with these statuses are removed from the
# candidate pool entirely. Anything between (Q / DTD / Probable) stays
# eligible but its estimated score is multiplied by play probability so
# uncertainty maps onto EV.
HARD_OUT_STATUSES = ("Out", "Doubtful", "Out For Season", "Suspended")

# Kept for backward compat (older code paths still reference it). Mirrors
# HARD_OUT_STATUSES — Q/DTD are no longer hard-excluded.
UNAVAILABLE_STATUSES = HARD_OUT_STATUSES


def play_probability(status: str | None) -> float:
    """Return the modeled probability that a player will play given his
    current injury_status string. Defaults to 1.0 when status is None or
    unknown (clean rotation player)."""
    if not status:
        return 1.0
    return INJURY_PLAY_PROBABILITY.get(status, 1.0)


def dnp_risk_factor(recent_logs: list[dict]) -> float:
    """Probability multiplier for an unflagged DNP pattern.

    ESPN's injury feed lags: a player benched the last game can still
    show injury_status=NULL when the recommendations are computed. This
    looks at the 3 most recent gamelogs' minutes (recent_logs ordered
    most-recent-first) and downweights candidates who have been on the
    sideline regardless of what ESPN says.

    Returns 1.0 when the pattern is clean. Compounds multiplicatively
    with play_probability so a Q player who just missed gets a double
    haircut.
    """
    if not recent_logs:
        return 1.0
    last3 = recent_logs[:3]
    dnp = sum(1 for log in last3 if (log.get("minutes") or 0) == 0)
    if len(last3) < 3:
        if dnp == len(last3) and dnp >= 1:
            return 0.55
        return 1.0
    if dnp == 3:
        return 0.30
    if dnp == 2:
        return 0.55
    if dnp == 1:
        most_recent_dnp = (last3[0].get("minutes") or 0) == 0
        return 0.75 if most_recent_dnp else 0.90
    return 1.0

# Playoff strategy: burn threshold
# If best future spot > tonight + 10%, recommend saving
BURN_THRESHOLD = 0.10

# Minimum average minutes over the last 10 games for a player to be a
# candidate. Below this, DNP/garbage-time outliers dominate the signal and
# we don't want the engine to propose them.
MIN_MINUTES_L10 = 12

# Feature flag — when true, compute_performance_score blends the
# defender-vs-player rate from `matchup_aggregates` into matchup_factor.
# Off by default until backfill has populated enough data and we've
# eyeballed a few syncs.
USE_PAIR_MATCHUP = os.environ.get("USE_PAIR_MATCHUP", "").lower() in ("1", "true", "yes")


# Watchlist priority boosts on estimated_score (multiplicative).
# Priority 1 dominates so the franchise pick wins close calls;
# 2 and 3 stay nudges only.
WATCHLIST_BASE = {1: 0.20, 2: 0.08, 3: 0.03}
# Extra boost when the player's team is at elimination risk.
# 'critical' = next loss ends the series; 'high' = facing a 2-3 deficit.
WATCHLIST_ELIM_BONUS = {"critical": 0.35, "high": 0.15, "none": 0.0}
# Challenger Game 3 at home after 0-2 deficit — watchlist players only.
WATCHLIST_GAME3_SURGE = 1.12


# ---------- Team save tax (Finals dignity hedge) ----------
#
# When a team's elite pool has been thinned by R1/R2 cramages, the user
# wants to preserve specific top performers (not necessarily all top-N)
# so Finals doesn't collapse into a 2nd-tier filler purgatory if that
# team advances. We encode this by **penalizing** (multiplying down)
# specific ranks of each team in the weekly_plan optimization so the
# Hungarian solver defers them — unless an elimination trigger fires.
#
# TEAM_SAVE_RANKS: list of ranks (0 = highest season avg among
# non-cramed teammates) that should be saved. Lets the user say "save
# rank 1 but let rank 0 burn at peak" (a SAS/CLE pattern where the top
# is intended to burn at G2-G3 home spots while the second-best is
# preserved for Finals).
#
# Example (R3 2026 state, post-2026-05-22):
#   NYK lost KAT+OG_Anunoby+Hart → only ★★★ left is Brunson, must save
#     → ranks [0]
#   OKC lost Hartenstein+A.Mitchell+Holmgren → save BOTH remaining top
#     2 (SGA + J. Williams)
#     → ranks [0, 1]
#   SAS lost Wemby+Castle → user framework "burn Fox at G3 peak, save
#     Harper for Finals" → tax rank 1 only, leave rank 0 burnable
#     → ranks [1]
#   CLE lost Mobley+Harden → user framework "burn Mitchell at G3 peak,
#     save Allen for Finals" → tax rank 1 only
#     → ranks [1]
TEAM_SAVE_RANKS: dict[str, list[int]] = {
    "NYK": [0],
    "OKC": [0, 1],
    "SAS": [1],
    "CLE": [1],
}

# Base intensity of the save penalty (0 = no save, 1 = fully blocked).
# Heavier per team = stronger insistence on preserving them. Calibrated
# so the protected ranks' value at G2-G3 drops below mid-tier
# alternatives (forcing the Hungarian solver to defer to G6+ or
# Finals), while the step decay (see save_tax_for_game) releases the
# tax progressively in late-series spots.
TEAM_SAVE_TAX_BASE: dict[str, float] = {
    "NYK": 0.95,  # Brunson sole ★★★ — must save until G6+/Finals
    "OKC": 0.92,  # Save both SGA + J. Williams
    "SAS": 0.90,  # Save Harper specifically; Fox burnable at peak
    "CLE": 0.90,  # Save Allen specifically; Mitchell burnable at peak
}


def save_tax_for_game(
    team: str,
    player_team_rank: int,
    game_number: int | None,
    elim: str,
) -> float:
    """Return the multiplicative save penalty fraction for a candidate cell.

    The save tax follows a step-down schedule across the series. Heavy
    in G2-G3 (defer aggressively), medium in G4, light at G5 (burn if
    no good alternative), near-zero at G6 (most series-deciders), and
    fully released at G7 or critical elimination (must-win-or-lose).

    The schedule (calibrated so protected elites stay below mid-tier
    alternatives until at least G5, then release progressively):
        G2/G3 : base × 1.0    (full save — no chance of burn)
        G4    : base × 0.80   (medium — defer unless no alternative)
        G5    : base × 0.65   (close call — may burn vs weak alt)
        G6    : base × 0.30   (mostly release — protected burns here)
        G7+   : 0             (full burn — last chance)
        crit  : 0             (release on elimination game)

    Returns a value in [0, 1] applied as `final_score *= (1 - tax)`.

    Args:
        team: Player's team abbreviation.
        player_team_rank: Player's rank within his non-cramed teammates,
            0 = highest season avg. Anyone outside TEAM_SAVE_RANKS gets
            tax=0 (i.e. is freely burnable).
        game_number: 1..7 (None = unknown/Finals).
        elim: "critical" | "high" | "none" — pulled from elimination_risk.
    """
    saved_ranks = TEAM_SAVE_RANKS.get(team) or []
    if player_team_rank not in saved_ranks:
        return 0.0
    if elim == "critical":
        return 0.0
    if game_number is None:
        return 0.0
    if game_number >= 7:
        return 0.0
    base = TEAM_SAVE_TAX_BASE.get(team, 0.5)
    if game_number == 6:
        return base * 0.40
    if game_number == 5:
        return base * 0.75
    if game_number == 4:
        return base * 0.90
    return base  # G2 and G3 — full save
