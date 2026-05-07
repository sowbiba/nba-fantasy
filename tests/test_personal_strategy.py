from sync.personal_strategy import (
    PersonalContext,
    compute_multiplier,
    is_hot,
)


def _ctx(**overrides) -> PersonalContext:
    """Default neutral context, overridable per test."""
    base = dict(
        save_rank=None,
        team_outlook=None,
        home_save_top=True,
        is_home_game=True,
        elimination_risk="none",
        avg_l5=20.0,
        season_avg=20.0,
    )
    base.update(overrides)
    return PersonalContext(**base)


# --- is_hot --------------------------------------------------------------


def test_is_hot_threshold():
    assert is_hot(avg_l5=24.1, season_avg=20.0) is True
    assert is_hot(avg_l5=23.9, season_avg=20.0) is False


def test_is_hot_zero_season():
    assert is_hot(avg_l5=30, season_avg=0) is False


# --- Defaults / missing data --------------------------------------------


def test_no_outlook_returns_neutral():
    mult, reason = compute_multiplier(_ctx(team_outlook=None, save_rank=1))
    assert mult == 1.0
    assert reason == "no_outlook"


def test_no_rank_returns_neutral():
    mult, reason = compute_multiplier(_ctx(team_outlook="advance", save_rank=None))
    assert mult == 1.0
    assert reason == "no_rank"


def test_unknown_outlook_falls_back_to_neutral():
    mult, reason = compute_multiplier(_ctx(team_outlook="???", save_rank=1))
    assert mult == 1.0
    assert reason == "unknown_outlook"


# --- Advance (save the top) ---------------------------------------------


def test_advance_rank1_strong_save():
    mult, reason = compute_multiplier(_ctx(team_outlook="advance", save_rank=1))
    assert mult == 0.40
    assert reason == "save_advance_r1"


def test_advance_rank2_moderate_save():
    mult, _ = compute_multiplier(_ctx(team_outlook="advance", save_rank=2))
    assert mult == 0.60


def test_advance_rank3_light_save():
    mult, _ = compute_multiplier(_ctx(team_outlook="advance", save_rank=3))
    assert mult == 0.80


def test_advance_rank4plus_no_penalty():
    mult, reason = compute_multiplier(_ctx(team_outlook="advance", save_rank=5))
    assert mult == 1.0
    assert reason == "burn_advance"


def test_advance_hot_relief_halves_penalty():
    """Hot rank-1 should not be buried by the save penalty."""
    mult, reason = compute_multiplier(_ctx(
        team_outlook="advance", save_rank=1, avg_l5=30, season_avg=20,
    ))
    # 0.40 → halfway to 1.0 = 0.70
    assert mult == 0.70
    assert reason == "save_advance_r1_hot"


# --- Eliminate (use everyone, prefer home for top picks) ----------------


def test_eliminate_rank1_at_home_gets_boost():
    mult, reason = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=1, is_home_game=True,
    ))
    assert mult == 1.10
    assert reason == "eliminate_home_r1"


def test_eliminate_rank1_on_road_mild_penalty():
    mult, reason = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=1, is_home_game=False,
    ))
    assert mult == 0.90
    assert reason == "eliminate_away_r1"


def test_eliminate_rank3_neutral_regardless_of_venue():
    """Mid/lower ranks aren't bound to home/away preference."""
    mult_home, _ = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=3, is_home_game=True,
    ))
    mult_away, _ = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=3, is_home_game=False,
    ))
    assert mult_home == 1.0
    assert mult_away == 1.0


def test_eliminate_home_save_top_off_neutralizes():
    """If user opted out of home saving, no nudge applies even on top ranks."""
    mult, _ = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=1, is_home_game=False,
        home_save_top=False,
    ))
    assert mult == 1.0


def test_eliminate_away_hot_softens_wait_signal():
    """Hot rank-1 on the road shouldn't be told to wait."""
    mult, reason = compute_multiplier(_ctx(
        team_outlook="eliminate", save_rank=1, is_home_game=False,
        avg_l5=30, season_avg=20,
    ))
    # 0.90 → halfway to 1.0 = 0.95
    assert mult == 0.95
    assert "_hot" in reason


# --- Tossup (mid-list bias) ---------------------------------------------


def test_tossup_rank1_slight_save():
    mult, reason = compute_multiplier(_ctx(team_outlook="tossup", save_rank=1))
    assert mult == 0.85
    assert reason.startswith("tossup_save")


def test_tossup_rank3_midlist_boost():
    mult, reason = compute_multiplier(_ctx(team_outlook="tossup", save_rank=3))
    assert mult == 1.05
    assert reason.startswith("tossup_midlist")


def test_tossup_rank5plus_slight_penalty():
    mult, _ = compute_multiplier(_ctx(team_outlook="tossup", save_rank=6))
    assert mult == 0.95


# --- Elimination override -----------------------------------------------


def test_critical_elimination_releases_save_and_boosts():
    """Even an advance-r1 save should flip to a boost when the team
    might be gone tomorrow."""
    mult, reason = compute_multiplier(_ctx(
        team_outlook="advance", save_rank=1, elimination_risk="critical",
    ))
    assert mult == 1.20
    assert reason == "elim_critical_release"


def test_high_elimination_releases_save():
    mult, reason = compute_multiplier(_ctx(
        team_outlook="advance", save_rank=1, elimination_risk="high",
    ))
    assert mult == 1.05
    assert reason == "elim_high_release"


# --- Clamping -----------------------------------------------------------


def test_multiplier_clamped_to_floor():
    """Even with worst-case inputs, multiplier stays ≥ 0.40."""
    mult, _ = compute_multiplier(_ctx(team_outlook="advance", save_rank=1))
    assert mult >= 0.40


def test_multiplier_clamped_to_ceiling():
    """Even with best-case inputs, multiplier stays ≤ 1.30."""
    mult, _ = compute_multiplier(_ctx(
        team_outlook="advance", save_rank=1, elimination_risk="critical",
    ))
    assert mult <= 1.30
