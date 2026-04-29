import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ESPN injury endpoint template
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# NBA API request delay (avoid rate limiting)
NBA_API_DELAY = 0.6  # seconds between requests

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
