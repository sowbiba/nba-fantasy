from sync.scoring import (
    weighted_ttfl_average,
    matchup_factor,
    home_away_factor,
    fatigue_factor,
    trend_factor,
    consistency_factor,
    compute_performance_score,
    league_avg_by_position,
    position_def_column,
)


def test_position_def_column():
    assert position_def_column("G") == "vs_guards_ttfl_avg"
    assert position_def_column("F") == "vs_forwards_ttfl_avg"
    assert position_def_column("C") == "vs_centers_ttfl_avg"
    assert position_def_column("G-F") == "vs_centers_ttfl_avg"  # unknown → centers


def test_league_avg_by_position_means():
    rows = [
        {"vs_guards_ttfl_avg": 8.0, "vs_forwards_ttfl_avg": 10.0, "vs_centers_ttfl_avg": 12.0},
        {"vs_guards_ttfl_avg": 12.0, "vs_forwards_ttfl_avg": 14.0, "vs_centers_ttfl_avg": 16.0},
    ]
    means = league_avg_by_position(rows)
    assert means["vs_guards_ttfl_avg"] == 10.0
    assert means["vs_forwards_ttfl_avg"] == 12.0
    assert means["vs_centers_ttfl_avg"] == 14.0


def test_league_avg_by_position_skips_falsy_and_uses_default():
    rows = [{"vs_guards_ttfl_avg": 0, "vs_forwards_ttfl_avg": None, "vs_centers_ttfl_avg": 11.0}]
    means = league_avg_by_position(rows, default=10.5)
    assert means["vs_guards_ttfl_avg"] == 10.5   # all falsy → default
    assert means["vs_forwards_ttfl_avg"] == 10.5  # None → default
    assert means["vs_centers_ttfl_avg"] == 11.0


def test_weighted_average_full_data():
    # (60*3 + 55*2 + 50*1) / 6 = 340 / 6
    score = weighted_ttfl_average(avg_l5=60, avg_l10=55, avg_l20=50)
    assert round(score, 2) == 56.67

def test_weighted_average_low_stats():
    score = weighted_ttfl_average(avg_l5=0, avg_l10=0, avg_l20=0)
    assert score == 0

def test_matchup_factor_easy():
    factor = matchup_factor(opponent_ttfl_at_position=44, league_avg_ttfl_at_position=40)
    assert round(factor, 2) == 1.10

def test_matchup_factor_tough():
    factor = matchup_factor(opponent_ttfl_at_position=36, league_avg_ttfl_at_position=40)
    assert round(factor, 2) == 0.90

def test_home_away_home_game():
    factor = home_away_factor(home_avg=55, away_avg=48, season_avg=51, is_home=True)
    assert round(factor, 3) == 1.078

def test_home_away_away_game():
    factor = home_away_factor(home_avg=55, away_avg=48, season_avg=51, is_home=False)
    assert round(factor, 3) == 0.941

def test_home_away_capped_high():
    # +63% home split must be capped at +15%.
    factor = home_away_factor(home_avg=49, away_avg=20, season_avg=30, is_home=True)
    assert round(factor, 3) == 1.15

def test_home_away_capped_low():
    # -50% away split capped at -15%.
    factor = home_away_factor(home_avg=40, away_avg=15, season_avg=30, is_home=False)
    assert round(factor, 3) == 0.85

def test_fatigue_b2b():
    factor = fatigue_factor(days_rest=0)
    assert factor == 0.92

def test_fatigue_well_rested():
    factor = fatigue_factor(days_rest=3)
    assert factor == 1.03

def test_fatigue_normal():
    assert fatigue_factor(days_rest=1) == 1.0
    assert fatigue_factor(days_rest=2) == 1.0

def test_trend_positive():
    scores = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58]
    factor = trend_factor(recent_scores=scores)
    assert factor > 1.0

def test_trend_negative():
    scores = [58, 56, 54, 52, 50, 48, 46, 44, 42, 40]
    factor = trend_factor(recent_scores=scores)
    assert factor < 1.0

def test_trend_flat():
    scores = [50, 50, 50, 50, 50]
    factor = trend_factor(recent_scores=scores)
    assert round(factor, 2) == 1.0

def test_consistency_reliable():
    factor = consistency_factor(stddev=5, avg=50)
    assert factor > 1.0

def test_consistency_volatile():
    factor = consistency_factor(stddev=20, avg=50)
    assert factor < 1.0

def test_compute_performance_score():
    score = compute_performance_score(
        avg_l5=60, avg_l10=55, avg_l20=50,
        opponent_ttfl_at_position=44, league_avg_ttfl_at_position=40,
        home_avg=55, away_avg=48, season_avg=51, is_home=True,
        days_rest=2,
        recent_scores=[50, 52, 54, 56, 58, 55, 53, 51, 49, 47],
        stddev=8,
    )
    assert isinstance(score, float)
    assert score > 0
