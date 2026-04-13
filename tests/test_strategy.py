from sync.strategy import (
    classify_tiers,
    estimate_remaining_game_days,
    should_burn_elite,
    compute_strategy_adjustment,
)


def test_classify_tiers_basic():
    player_scores = [(i, 100 - i) for i in range(1, 51)]
    tiers = classify_tiers(player_scores)
    assert tiers[1] == "elite"
    assert tiers[10] == "elite"
    assert tiers[11] == "solid"
    assert tiers[25] == "solid"
    assert tiers[26] == "filler"
    assert tiers[50] == "filler"

def test_estimate_remaining_game_days():
    active_series = [
        {"home_wins": 2, "away_wins": 2, "round": 1},
        {"home_wins": 3, "away_wins": 1, "round": 1},
    ]
    days = estimate_remaining_game_days(active_series, current_round=1)
    assert days > 0
    assert isinstance(days, int)

def test_should_burn_elite_good_spot():
    result = should_burn_elite(
        tonight_score=75, best_future_score=70,
        elites_remaining=3, game_days_remaining=10,
    )
    assert result is True

def test_should_burn_elite_save():
    result = should_burn_elite(
        tonight_score=60, best_future_score=80,
        elites_remaining=2, game_days_remaining=15,
    )
    assert result is False

def test_strategy_adjustment_playoffs():
    adjusted = compute_strategy_adjustment(
        perf_score=70, tier="elite", is_home=True,
        series_score=(2, 2), elites_remaining=3, game_days_remaining=15,
    )
    assert isinstance(adjusted, float)
    assert adjusted > 70

def test_strategy_adjustment_filler_no_boost():
    adjusted = compute_strategy_adjustment(
        perf_score=40, tier="filler", is_home=False,
        series_score=(3, 1), elites_remaining=3, game_days_remaining=15,
    )
    assert adjusted <= 40
