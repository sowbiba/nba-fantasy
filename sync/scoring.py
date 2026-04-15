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


def weighted_ttfl_average(avg_l5: float, avg_l10: float, avg_l20: float) -> float:
    return (avg_l5 * 3 + avg_l10 * 1 + avg_l20 * 2) / 6


def matchup_factor(opponent_ttfl_at_position: float, league_avg_ttfl_at_position: float) -> float:
    if league_avg_ttfl_at_position == 0:
        return 1.0
    return opponent_ttfl_at_position / league_avg_ttfl_at_position


def home_away_factor(home_avg: float, away_avg: float, season_avg: float, is_home: bool) -> float:
    if season_avg == 0:
        return 1.0
    relevant_avg = home_avg if is_home else away_avg
    delta = (relevant_avg - season_avg) / season_avg
    return 1.0 + delta


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
) -> float:
    base = weighted_ttfl_average(avg_l5, avg_l10, avg_l20)
    factors = {
        "matchup": matchup_factor(opponent_ttfl_at_position, league_avg_ttfl_at_position),
        "home_away": home_away_factor(home_avg, away_avg, season_avg, is_home),
        "fatigue": fatigue_factor(days_rest),
        "trend": trend_factor(recent_scores),
        "consistency": consistency_factor(stddev, season_avg),
    }
    combined_multiplier = 1.0
    non_base_total_weight = sum(WEIGHTS[k] for k in factors.keys())
    for key, factor_value in factors.items():
        normalized_weight = WEIGHTS[key] / non_base_total_weight
        # Guard against negative factors that produce complex numbers when raised to fractional powers
        safe_factor = max(0.01, float(factor_value))
        combined_multiplier *= safe_factor ** normalized_weight
    return float(base * combined_multiplier)
