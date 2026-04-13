"""Playoff strategy layer.
Manages player capital (elite/solid/filler tiers),
estimates remaining game days, and decides burn-or-save.
"""
from sync.config import BURN_THRESHOLD


def classify_tiers(player_scores: list[tuple[int, float]]) -> dict[int, str]:
    sorted_players = sorted(player_scores, key=lambda x: x[1], reverse=True)
    tiers = {}
    for rank, (player_id, _) in enumerate(sorted_players, start=1):
        if rank <= 10:
            tiers[player_id] = "elite"
        elif rank <= 25:
            tiers[player_id] = "solid"
        else:
            tiers[player_id] = "filler"
    return tiers


def estimate_remaining_game_days(active_series: list[dict], current_round: int) -> int:
    remaining = 0
    for series in active_series:
        hw = series["home_wins"]
        aw = series["away_wins"]
        max_wins = max(hw, aw)
        played = hw + aw
        min_left = 4 - max_wins
        max_left = 7 - played
        est = (min_left + max_left) / 2
        remaining += max(0, est)
    future_rounds = 4 - current_round
    remaining += future_rounds * 6
    game_days = int(remaining * 0.7)
    return max(1, game_days)


def should_burn_elite(
    tonight_score: float, best_future_score: float,
    elites_remaining: int, game_days_remaining: int,
) -> bool:
    if best_future_score > tonight_score * (1 + BURN_THRESHOLD):
        return False
    if elites_remaining <= 2 and game_days_remaining > 10:
        return tonight_score >= best_future_score
    return True


def compute_strategy_adjustment(
    perf_score: float, tier: str, is_home: bool,
    series_score: tuple[int, int],
    elites_remaining: int, game_days_remaining: int,
) -> float:
    adjustment = 1.0
    hw, aw = series_score
    series_tight = abs(hw - aw) <= 1

    if is_home:
        adjustment += 0.03
        if series_tight:
            adjustment += 0.02

    if (hw == 3 or aw == 3) and tier != "filler":
        adjustment += 0.08

    if tier == "elite":
        elite_ratio = elites_remaining / max(1, game_days_remaining)
        if elite_ratio < 0.2:
            adjustment -= 0.05
    elif tier == "filler":
        elite_ratio = elites_remaining / max(1, game_days_remaining)
        if elite_ratio < 0.25:
            adjustment += 0.03

    if not is_home:
        adjustment -= 0.03

    return perf_score * adjustment
