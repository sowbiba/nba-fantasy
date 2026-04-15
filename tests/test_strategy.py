from sync.strategy import (
    classify_tiers,
    estimate_remaining_game_days,
    should_burn_elite,
    compute_strategy_adjustment,
    elimination_risk,
)


def test_elimination_risk_critical_home():
    """Player's team at home, series (1, 3) - they have 1 win, opponent has 3 → elimination"""
    assert elimination_risk(series_score=(1, 3), player_is_home=True) == "critical"


def test_elimination_risk_critical_away():
    """Player's team away, series (3, 1) - home won 3, player team has 1 → elimination"""
    assert elimination_risk(series_score=(3, 1), player_is_home=False) == "critical"


def test_elimination_risk_none_leading():
    """Player's team leads 3-1 → no risk, they can be eliminated in the OTHER direction only if they lose 3 straight"""
    assert elimination_risk(series_score=(3, 1), player_is_home=True) == "none"


def test_elimination_risk_tied():
    """Series 2-2 → high risk (next loss puts them 2-3)"""
    assert elimination_risk(series_score=(2, 2), player_is_home=True) == "high"


def test_should_burn_elite_critical_elimination_forces_burn():
    """Even if future spot looks better, critical elimination forces burn"""
    result = should_burn_elite(
        tonight_score=50, best_future_score=80,
        elites_remaining=5, game_days_remaining=20,
        elimination="critical",
    )
    assert result is True


def test_strategy_adjustment_critical_elimination_boost():
    """Critical elimination gives a large boost (+15%)"""
    base = compute_strategy_adjustment(
        perf_score=50, tier="solid", is_home=True,
        series_score=(1, 3), elites_remaining=5, game_days_remaining=15,
    )
    with_elim = compute_strategy_adjustment(
        perf_score=50, tier="solid", is_home=True,
        series_score=(1, 3), elites_remaining=5, game_days_remaining=15,
        elimination="critical",
    )
    assert with_elim > base
    assert with_elim >= base * 1.1  # at least +10% on top of base





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
