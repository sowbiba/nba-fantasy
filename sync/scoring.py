"""6-factor performance scoring engine.

Factors and weights (from config):
  - weighted_avg:  35%  (L5×3 + L10×2 + L20×1) / 6
  - matchup:       25%  TTFL allowed by opponent at position
  - home_away:     10%  home/away split delta
  - fatigue:       10%  back-to-back / rest days
  - trend:         10%  linear regression slope on L10
  - consistency:   10%  stddev-based reliability
"""
import numpy as np
from sync.config import WEIGHTS, FATIGUE


# team_defense column holding TTFL allowed to each position.
POS_DEF_COLUMN = {
    "G": "vs_guards_ttfl_avg",
    "F": "vs_forwards_ttfl_avg",
    "C": "vs_centers_ttfl_avg",
}


def position_def_column(position: str) -> str:
    """Defense column for a player's position (anything non-G/F → centers)."""
    return POS_DEF_COLUMN.get(position, "vs_centers_ttfl_avg")


def league_avg_by_position(defense_rows, default: float = 10.5) -> dict[str, float]:
    """League-mean TTFL allowed at each position, keyed by team_defense
    column name — the *denominator* of the matchup factor.

    Computed from the live `team_defense` rows so it tracks the season and
    stays on the same scale (~8-13) as the vs_*_ttfl_avg numerators. A
    hardcoded denominator (the old 40) silently crushes every matchup factor.
    `default` is used only for a position whose column is entirely empty.
    """
    rows = list(defense_rows)
    out: dict[str, float] = {}
    for col in POS_DEF_COLUMN.values():
        vals = [r[col] for r in rows if r.get(col)]
        out[col] = sum(vals) / len(vals) if vals else default
    return out


def weighted_ttfl_average(avg_l5: float, avg_l10: float, avg_l20: float) -> float:
    # L5 dominates (50%), L10 reinforces (33%), L20 anchors (17%).
    # Skews recent: in playoffs, the L20 quickly fills with playoff games
    # round after round, while regular-season residue stops dragging picks.
    return (avg_l5 * 3 + avg_l10 * 2 + avg_l20 * 1) / 6


def minutes_adjusted_base(recent_logs: list[dict], season_avg: float) -> float:
    """Projected TTFL = recent efficiency (TTFL/min) × expected minutes.

    `recent_logs` is most-recent-first and MUST include DNP rows (minutes=0).
    This self-corrects the two blind spots of the DNP-excluded L5/L10 averages:

      - Role change: a starter dropped to bench minutes (e.g. a teammate
        returns from injury) sees `expected minutes` fall, so the projection
        tracks the new role instead of carrying his old high-minute games.
      - Injury / DNP: recent zero-minute games pull `expected minutes` toward
        0, so a sidelined player projects ≈0 even if his last *played* games
        (and thus his L5) still look strong.

    Recency-weighted with a 0.5 decay so the last 2-3 games dominate. Falls
    back to `season_avg` with no data; returns 0 when every recent game is a DNP.
    A steady starter reproduces his usual average (efficiency × stable minutes).
    """
    if not recent_logs:
        return season_avg
    logs = recent_logs[:8]
    weights = [0.5 ** i for i in range(len(logs))]  # 1, .5, .25 … most-recent first
    exp_min = sum((l.get("minutes") or 0) * w for l, w in zip(logs, weights)) / sum(weights)
    played = [(l, w) for l, w in zip(logs, weights) if (l.get("minutes") or 0) > 0]
    if not played:
        return 0.0
    num = sum((l.get("ttfl_score") or 0) * w for l, w in played)
    den = sum(l["minutes"] * w for l, w in played)
    if den <= 0:
        return season_avg
    return (num / den) * exp_min


def matchup_factor(
    opponent_ttfl_at_position: float,
    league_avg_ttfl_at_position: float,
    pair_allowed_off_ttfl_per36: float | None = None,
    pair_minutes_total: float = 0.0,
    player_off_avg_per36: float = 0.0,
) -> float:
    """Adaptive matchup factor.

    Falls back to the team-positional average when there's no in-series
    pair sample (R1 G1, or pre-backfill). As soon as a real defender vs
    this player has accumulated minutes, the factor blends in his
    suppression rate, weighted by confidence:

        confidence = clamp((minutes - 5) / 55, 0, 1)
        factor = team_factor × (1 - c) + pair_factor × c

    pair_factor uses *offensive-only* TTFL (PTS + AST + FG/3P/FT − misses
    − TOV) so REB/STL/BLK_BY — which aren't matchup-attributable — don't
    distort the comparison.
    """
    if league_avg_ttfl_at_position == 0:
        team_factor = 1.0
    else:
        team_factor = opponent_ttfl_at_position / league_avg_ttfl_at_position

    if (
        pair_allowed_off_ttfl_per36 is None
        or pair_minutes_total < 5
        or player_off_avg_per36 <= 0
    ):
        return team_factor

    pair_factor = pair_allowed_off_ttfl_per36 / player_off_avg_per36
    confidence = max(0.0, min(1.0, (pair_minutes_total - 5) / 55.0))
    return team_factor * (1 - confidence) + pair_factor * confidence


def home_away_factor(home_avg: float, away_avg: float, season_avg: float, is_home: bool) -> float:
    if season_avg == 0:
        return 1.0
    relevant_avg = home_avg if is_home else away_avg
    delta = (relevant_avg - season_avg) / season_avg
    # Cap at ±15% like the other situational factors — a home/away split
    # shouldn't single-handedly swing the projection (sample-size guard lives
    # in fetcher.compute_player_aggregates, which neutralizes thin splits).
    capped = max(-0.15, min(0.15, delta))
    return 1.0 + capped


def fatigue_factor(days_rest: int) -> float:
    if days_rest == 0:
        return 1.0 + FATIGUE["b2b"]
    elif days_rest >= 3:
        return 1.0 + FATIGUE["rest_3plus"]
    return 1.0


def trend_factor(recent_scores: list[int | float]) -> float:
    if len(recent_scores) < 3:
        return 1.0
    scores = list(recent_scores[:10])
    x = np.arange(len(scores), dtype=float)
    y = np.array(scores, dtype=float)
    try:
        with np.errstate(all="ignore"):
            slope = float(np.real(np.polyfit(x, y, 1)[0]))
    except (np.linalg.LinAlgError, ValueError):
        return 1.0
    avg = float(np.mean(y))
    if avg == 0 or not np.isfinite(slope):
        return 1.0
    pct_change = slope / avg
    capped = max(-0.10, min(0.10, pct_change))
    return 1.0 + capped


def consistency_factor(stddev: float, avg: float) -> float:
    if avg == 0:
        return 1.0
    cv = stddev / avg
    deviation = 0.25 - cv
    modifier = deviation * 0.20
    capped = max(-0.05, min(0.05, modifier))
    return 1.0 + capped


def compute_performance_score(
    avg_l5: float, avg_l10: float, avg_l20: float,
    opponent_ttfl_at_position: float, league_avg_ttfl_at_position: float,
    home_avg: float, away_avg: float, season_avg: float, is_home: bool,
    days_rest: int,
    recent_scores: list[int | float],
    stddev: float,
    pair_allowed_off_ttfl_per36: float | None = None,
    pair_minutes_total: float = 0.0,
    player_off_avg_per36: float = 0.0,
    base_override: float | None = None,
) -> float:
    # base_override lets the caller pass a minutes-adjusted projection
    # (see minutes_adjusted_base); falls back to the classic L5/L10/L20 blend.
    base = base_override if base_override is not None else weighted_ttfl_average(avg_l5, avg_l10, avg_l20)
    factors = {
        "matchup": matchup_factor(
            opponent_ttfl_at_position,
            league_avg_ttfl_at_position,
            pair_allowed_off_ttfl_per36=pair_allowed_off_ttfl_per36,
            pair_minutes_total=pair_minutes_total,
            player_off_avg_per36=player_off_avg_per36,
        ),
        "home_away": home_away_factor(home_avg, away_avg, season_avg, is_home),
        "fatigue": fatigue_factor(days_rest),
        "trend": trend_factor(recent_scores),
        # Consistency is a recency signal → measured against L10 form, not the
        # whole-season mean (which in playoffs still carries regular-season
        # residue). Falls back to season_avg when L10 isn't available.
        "consistency": consistency_factor(stddev, avg_l10 or season_avg),
    }
    combined_multiplier = 1.0
    non_base_total_weight = sum(WEIGHTS[k] for k in factors.keys())
    for key, factor_value in factors.items():
        normalized_weight = WEIGHTS[key] / non_base_total_weight
        # Guard against negative factors that produce complex numbers when raised to fractional powers
        safe_factor = max(0.01, float(factor_value))
        combined_multiplier *= safe_factor ** normalized_weight
    return float(base * combined_multiplier)
