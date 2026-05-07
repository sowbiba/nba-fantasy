from sync.config import dnp_risk_factor


def _logs(*minutes):
    """Build gamelog dicts ordered most-recent-first, like db.get_player_game_logs."""
    return [{"minutes": m} for m in minutes]


def test_no_logs_returns_one():
    assert dnp_risk_factor([]) == 1.0


def test_clean_three_games_returns_one():
    assert dnp_risk_factor(_logs(32, 28, 30)) == 1.0


def test_three_consecutive_dnp_strongest_penalty():
    assert dnp_risk_factor(_logs(0, 0, 0)) == 0.30


def test_two_of_three_dnp_mid_penalty():
    assert dnp_risk_factor(_logs(0, 0, 25)) == 0.55
    assert dnp_risk_factor(_logs(0, 25, 0)) == 0.55
    assert dnp_risk_factor(_logs(25, 0, 0)) == 0.55


def test_only_most_recent_dnp_is_higher_alert_than_older():
    """Missing the last game is a stronger signal than an older 0-min outing."""
    most_recent = dnp_risk_factor(_logs(0, 28, 30))
    older = dnp_risk_factor(_logs(28, 0, 30))
    assert most_recent == 0.75
    assert older == 0.90
    assert most_recent < older


def test_partial_history_all_dnp_flags():
    """Two-game history both DNP — flag even without 3 logs."""
    assert dnp_risk_factor(_logs(0, 0)) == 0.55
    assert dnp_risk_factor(_logs(0)) == 0.55


def test_partial_history_clean_does_not_flag():
    assert dnp_risk_factor(_logs(28, 30)) == 1.0
    assert dnp_risk_factor(_logs(28)) == 1.0


def test_handles_none_minutes_as_dnp():
    """A log row with minutes=None should count as DNP, not crash."""
    assert dnp_risk_factor([{"minutes": None}, {"minutes": None}, {"minutes": None}]) == 0.30


def test_ignores_logs_beyond_window():
    """Only the 3 most recent logs matter."""
    assert dnp_risk_factor(_logs(28, 30, 32, 0, 0, 0)) == 1.0
