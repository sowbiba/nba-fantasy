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
    minutes_adjusted_base,
)
from datetime import date as _date, timedelta as _timedelta


def _mlog(ttfl, minutes):
    return {"ttfl_score": ttfl, "minutes": minutes}


_TODAY = _date(2026, 5, 27)


def _dlog(ttfl, minutes, days_ago):
    return {
        "ttfl_score": ttfl,
        "minutes": minutes,
        "date": (_TODAY - _timedelta(days=days_ago)).isoformat(),
    }


def test_minutes_adjusted_empty_returns_season():
    assert minutes_adjusted_base([], season_avg=30.0) == 30.0


def test_minutes_adjusted_all_dnp_returns_zero():
    assert minutes_adjusted_base([_mlog(0, 0)] * 3, season_avg=30.0) == 0.0


def test_minutes_adjusted_stable_starter_reproduces_average():
    logs = [_mlog(45, 36) for _ in range(6)]
    assert abs(minutes_adjusted_base(logs, season_avg=45.0) - 45.0) < 0.5


def test_minutes_adjusted_role_drop_projects_low():
    # Bench role now (20min) after starting before (46min / 45 TTFL) — Harper pattern.
    logs = [_mlog(9, 20), _mlog(8, 20), _mlog(7, 18), _mlog(45, 46), _mlog(44, 44)]
    assert minutes_adjusted_base(logs, season_avg=30.0) < 15


def test_minutes_adjusted_recent_dnp_projects_near_zero():
    # Sidelined: 3 recent DNPs, one old big game — Jalen pattern.
    logs = [_mlog(0, 0), _mlog(0, 0), _mlog(0, 0), _mlog(7, 7), _mlog(35, 37)]
    assert minutes_adjusted_base(logs, season_avg=28.0) < 6


def test_minutes_adjusted_role_rise_projects_higher():
    # Playoff role bump (Caruso pattern): recent 28-31 min / 35-40 TTFL, low before.
    logs = [_mlog(39, 30), _mlog(35, 28), _mlog(40, 31), _mlog(12, 12), _mlog(8, 10)]
    assert minutes_adjusted_base(logs, season_avg=15.0) > 25


def test_minutes_adjusted_stale_only_returns_zero():
    # Out of rotation: last games are end-of-regular-season spikes 40+ days
    # ago (Carlson/Sandfort pattern) → projects 0, not the stale 40.
    logs = [_dlog(43, 42, 44), _dlog(39, 37, 46)]
    assert minutes_adjusted_base(logs, season_avg=11.0, today=_TODAY) == 0.0


def test_minutes_adjusted_recent_in_window_counts():
    logs = [_dlog(35, 30, 1), _dlog(40, 31, 3)]
    assert minutes_adjusted_base(logs, season_avg=12.0, today=_TODAY) > 25


def test_minutes_adjusted_drops_stale_keeps_recent():
    # One recent bench game + old starter spikes → only the recent one counts.
    logs = [_dlog(8, 14, 2), _dlog(43, 42, 44), _dlog(39, 37, 46)]
    assert minutes_adjusted_base(logs, season_avg=11.0, today=_TODAY) < 12


def test_minutes_adjusted_no_dates_skips_guard():
    # Date-less logs + today set → guard is skipped (graceful), projects normally.
    logs = [_mlog(45, 36) for _ in range(4)]
    assert abs(minutes_adjusted_base(logs, season_avg=45.0, today=_TODAY) - 45.0) < 0.5


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
