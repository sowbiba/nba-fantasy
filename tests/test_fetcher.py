from sync.fetcher import compute_player_aggregates


def _log(ttfl, minutes, is_home=True):
    return {"ttfl_score": ttfl, "minutes": minutes, "is_home": is_home}


def test_dnp_excluded():
    logs = [_log(40, 30), _log(0, 0), _log(20, 25)]
    agg = compute_player_aggregates(logs)
    # 0-minute game dropped → season = mean(40, 20) = 30
    assert agg["avg_ttfl_season"] == 30.0


def test_l5_cap_for_sub_rotation_player():
    """Bencher (low minutes) with an L5 spiked by 2 blowouts gets capped."""
    # avg_minutes_l10 ≈ 13 (< L5_CAP_MINUTES=20); L5 inflated to 45 while
    # season sits ~15 → cap to max(season*1.5, L10).
    logs = [_log(46, 40), _log(44, 38)] + [_log(6, 8) for _ in range(8)]
    agg = compute_player_aggregates(logs)
    season = agg["avg_ttfl_season"]
    # L5 must not exceed max(season*1.5, L10) and must be well under raw 45.
    assert agg["avg_ttfl_l5"] <= max(season * 1.5, agg["avg_ttfl_l10"]) + 1e-9
    assert agg["avg_ttfl_l5"] < 45


def test_l5_not_capped_for_starter():
    """A full-minute starter on a real hot streak keeps his L5."""
    logs = [_log(55, 36) for _ in range(5)] + [_log(30, 36) for _ in range(5)]
    agg = compute_player_aggregates(logs)
    # 36 min ≥ L5_CAP_MINUTES → no cap, L5 stays 55.
    assert agg["avg_ttfl_l5"] == 55.0


def test_home_away_sample_guard():
    """A thin home split (<4 games) falls back to season avg (neutral)."""
    logs = [_log(50, 30, is_home=True)] + [_log(20, 30, is_home=False) for _ in range(6)]
    agg = compute_player_aggregates(logs)
    # Only 1 home game → home_avg should equal season avg, not 50.
    assert agg["home_avg"] == agg["avg_ttfl_season"]
    assert agg["home_avg"] != 50.0
