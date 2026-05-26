"""Playoff strategy layer.
Manages player capital (elite/solid/filler tiers),
estimates remaining game days, and decides burn-or-save.
"""
from functools import lru_cache

from sync.config import BURN_THRESHOLD


# --- Reservation penalty (shared with weekly_plan) -------------------------
# Best-available : 0.0 neutralise la reservation tax (reco du jour ET
# weekly_plan). Était 0.55 — taxait les élites season_avg>28 et a contribué
# à la chute de moyenne 36.5→21.1 (feedback 2026-05-26). Remettre >0 pour
# réactiver la préservation d'élites multi-rounds.
MAX_RESERVATION_PENALTY = 0.0
ROUND_RESERVATION_FACTOR = {1: 1.0, 2: 0.55, 3: 0.2, 4: 0.0}

TEAM_POTENTIAL_TOP_SEED = 1.0
TEAM_POTENTIAL_LOW_SEED = 0.5
TEAM_POTENTIAL_UNKNOWN = 0.3


# Forecast blending: at series kickoff, user's prono weighs 40%. Its weight
# fades linearly to 0 after 4 games played (reality takes over).
FORECAST_MAX_WEIGHT = 0.4
FORECAST_FADE_GAMES = 4


# --- Probabilistic engine knobs -------------------------------------------
# K_VAR penalizes high-variance profiles when ranking candidates: the score
# the optimizer sees is `mean - K_VAR * stddev`, a Sharpe-like adjustment.
# 0.25 keeps stable elites unchanged but discounts volatile rookies enough
# that an alternative steady pick wins ties.
K_VAR = 0.25

# LAMBDA_RISK weights the loss-aversion term `(1 - pick_prob) * tier_value`.
# 0 = pure expected value, larger = the optimizer increasingly avoids picks
# whose game has a real chance of not happening. 0.6 lets a reliable G5 win
# over a volatile G7 even when raw EV is close.
LAMBDA_RISK = 0.6

# Capital value per watchlist tier (priority 1=★★★, 2=★★, 3=★). Used both as
# the weight in `waste_cost` and as the pool baseline. Calibrated on TTFL
# seasonal medians: elite ★★★ ≈ 35, solid ★★ ≈ 22, filler ★ ≈ 14.
TIER_CAPITAL_VALUE = {1: 35.0, 2: 22.0, 3: 14.0}

# Average games per round for unknown-bracket future rounds (R+1, R+2…).
# 4.5 is the unbiased estimator (between sweep at 4 and full G7).
EXPECTED_GAMES_PER_ROUND = 4.5


def _seed_team_potential(series: dict) -> tuple[float, float]:
    """Return (home_potential, away_potential) from seeding alone."""
    if series.get("round") == 1:
        return TEAM_POTENTIAL_TOP_SEED, TEAM_POTENTIAL_LOW_SEED
    if series.get("round", 1) >= 2:
        return TEAM_POTENTIAL_TOP_SEED, TEAM_POTENTIAL_TOP_SEED
    return TEAM_POTENTIAL_UNKNOWN, TEAM_POTENTIAL_UNKNOWN


def _forecast_weight(games_played: int) -> float:
    """Forecast weight fades from FORECAST_MAX_WEIGHT to 0 over FORECAST_FADE_GAMES."""
    fade = max(0.0, 1.0 - games_played / FORECAST_FADE_GAMES)
    return FORECAST_MAX_WEIGHT * fade


# --- Markov series probability helpers ------------------------------------
# A series is a state (home_wins, away_wins) with absorbing barriers at
# either side reaching 4. Given p_home (probability the home team wins any
# single game), we can answer:
#   - prob_game_played((hw,aw), n, p_home) — P that game n actually occurs
#   - prob_team_eliminated_this_round((hw,aw), p_team) — opponent reaches 4 first
#   - prob_team_advances((hw,aw), p_team) — team reaches 4 first
# All recurse over the 4×4 state space and are cached.

@lru_cache(maxsize=4096)
def _series_outcome(state: tuple[int, int], p_home: float) -> tuple[float, float, float]:
    """Return (P(home wins series), P(away wins series), expected games left)
    from the given (hw, aw) state. Cached.
    """
    hw, aw = state
    if hw >= 4:
        return 1.0, 0.0, 0.0
    if aw >= 4:
        return 0.0, 1.0, 0.0
    p_home_w, p_away_w_h, eg_h = _series_outcome((hw + 1, aw), p_home)
    p_home_w_a, p_away_w, eg_a = _series_outcome((hw, aw + 1), p_home)
    p_h = p_home * p_home_w + (1 - p_home) * p_home_w_a
    p_a = p_home * p_away_w_h + (1 - p_home) * p_away_w
    eg = 1.0 + p_home * eg_h + (1 - p_home) * eg_a
    return p_h, p_a, eg


@lru_cache(maxsize=4096)
def prob_game_played(
    state: tuple[int, int], target_game: int, p_home: float
) -> float:
    """P that the n-th game of the series actually occurs, from current state.
    target_game is 1-indexed (G1..G7). p_home is the home team's per-game win prob.
    """
    hw, aw = state
    played = hw + aw
    if target_game <= played:
        return 1.0  # already played (or this game is current)
    if target_game > 7:
        return 0.0
    if hw >= 4 or aw >= 4:
        return 0.0
    # Game n is played iff after n-1 total games, neither side has reached 4.
    # Recurse one game at a time.
    p_to_h = prob_game_played((hw + 1, aw), target_game, p_home)
    p_to_a = prob_game_played((hw, aw + 1), target_game, p_home)
    return p_home * p_to_h + (1 - p_home) * p_to_a


def prob_team_eliminated_this_round(
    state: tuple[int, int], p_team: float, team_is_home: bool
) -> float:
    """P that team is eliminated in the current series.
    p_team = probability the team wins any single game.
    """
    p_home = p_team if team_is_home else 1 - p_team
    p_h, p_a, _ = _series_outcome(state, p_home)
    return p_a if team_is_home else p_h


def prob_team_advances(
    state: tuple[int, int], p_team: float, team_is_home: bool
) -> float:
    """P that team wins the current series."""
    return 1.0 - prob_team_eliminated_this_round(state, p_team, team_is_home)


def expected_games_left_in_series(
    state: tuple[int, int], p_home: float
) -> float:
    """Expected number of games remaining in the series from `state`."""
    _, _, eg = _series_outcome(state, p_home)
    return eg


# --- Per-game team win probability ----------------------------------------
# Translates seed + user forecast into a single-game win probability. Used
# by the Markov chain. Defaults to 50/50 when nothing is known.
def team_single_game_win_prob(
    team: str, series: dict, forecast: dict | None
) -> float:
    """Probability that `team` wins any single game in this series."""
    if not series:
        return 0.5
    is_home = team == series.get("home_team")
    # Seed-based prior: in R1 the higher seed (home) is slight favorite.
    if series.get("round") == 1:
        seed_p = 0.55 if is_home else 0.45
    else:
        seed_p = 0.5

    if not forecast or not forecast.get("winner_team"):
        return seed_p

    # Map expected_games to per-game win prob for the forecasted winner.
    # Tighter series (G7) → closer to 50/50; sweep (G4) → strongly favored.
    expected_games = forecast.get("expected_games") or 6
    games_to_p = {4: 0.72, 5: 0.62, 6: 0.55, 7: 0.51}
    forecast_p_winner = games_to_p.get(expected_games, 0.55)
    forecasted_winner = forecast["winner_team"]
    forecast_p = (
        forecast_p_winner if team == forecasted_winner else 1 - forecast_p_winner
    )

    # Blend seed + forecast with the existing fade curve.
    played = (series.get("home_wins") or 0) + (series.get("away_wins") or 0)
    w = _forecast_weight(played)
    return (1 - w) * seed_p + w * forecast_p


# --- Expected playoff games left for a player ------------------------------
def expected_remaining_player_games(
    team: str,
    series: dict,
    current_round: int,
    forecasts: dict[int, dict] | None = None,
) -> float:
    """E[games this player's team still plays in the playoffs].

    Sum: tail of current series (Markov) + (P(advance) × games per future round).
    Future-round bracket isn't known, so we use EXPECTED_GAMES_PER_ROUND.
    """
    if not series:
        return EXPECTED_GAMES_PER_ROUND  # no info → neutral
    fc = (forecasts or {}).get(series.get("id"))
    p_team = team_single_game_win_prob(team, series, fc)
    is_home = team == series.get("home_team")
    p_home = p_team if is_home else 1 - p_team
    state = (series.get("home_wins") or 0, series.get("away_wins") or 0)

    games_in_series = expected_games_left_in_series(state, p_home)
    p_adv = prob_team_advances(state, p_team, is_home)

    rounds_after_this = max(0, 4 - current_round)
    # Each subsequent round is reached with a chance ~p_adv ^ k (rough proxy:
    # we assume similar opposition strength). Use geometric decay.
    future_games = 0.0
    p_reached = p_adv
    for _ in range(rounds_after_this):
        future_games += p_reached * EXPECTED_GAMES_PER_ROUND
        p_reached *= 0.5  # neutral prior for unknown future opponents

    return games_in_series + future_games


def compute_team_potential_scores(
    active_series: list[dict],
    forecasts: dict[int, dict] | None = None,
) -> dict[str, float]:
    """Translate playoff seeding (+ optional user forecasts) into a team-potential proxy.

    R1 home team = top seed (1-4) → high chance of advancing.
    R1 away team = lower seed (5-8) → moderate.
    R2+ teams → treat both as strong.

    If `forecasts[series_id]` contains `winner_team`, blend:
      potential = (1 - w) × seed_default + w × forecast_potential
    with `w` fading from 0.4 (before any game) to 0 (after 4 played).
    """
    forecasts = forecasts or {}
    scores: dict[str, float] = {}
    for s in active_series:
        seed_home, seed_away = _seed_team_potential(s)
        fc = forecasts.get(s.get("id")) if forecasts else None
        if not fc:
            scores[s["home_team"]] = seed_home
            scores[s["away_team"]] = seed_away
            continue
        played = (s.get("home_wins") or 0) + (s.get("away_wins") or 0)
        w = _forecast_weight(played)
        winner = fc.get("winner_team")
        fc_home = 1.0 if winner == s["home_team"] else 0.2
        fc_away = 1.0 if winner == s["away_team"] else 0.2
        scores[s["home_team"]] = (1 - w) * seed_home + w * fc_home
        scores[s["away_team"]] = (1 - w) * seed_away + w * fc_away
    return scores


def compute_reservation_penalty(
    player_season_avg: float,
    team_potential: float,
    round_num: int,
) -> float:
    """Heuristic reservation tax — kept for the daily reco path.

    `elite_factor` ramps from 0 (at 28 avg — league-average starter) to 1
    (at 40 avg — top-15 fantasy player).
    """
    if player_season_avg <= 28:
        return 0.0
    elite_factor = min(1.0, (player_season_avg - 28) / 12)
    round_factor = ROUND_RESERVATION_FACTOR.get(round_num, 0.0)
    raw = elite_factor * team_potential * round_factor
    return min(MAX_RESERVATION_PENALTY, raw * MAX_RESERVATION_PENALTY)


OPP_COST_PER_FUTURE_GAME = 0.06


def compute_opportunity_cost_fraction(
    expected_utility: float,
    expected_remaining_after: float,
    tier_demand_factor: float,
) -> float:
    """Probabilistic reservation tax based on expected future use.

    Linear scaling in expected_remaining_after × demand : each expected
    future game adds OPP_COST_PER_FUTURE_GAME to the reservation fraction.
    Capped at MAX_RESERVATION_PENALTY (0.55).

    The earlier saturating form `x/(1+x)` capped almost every player with
    >1 future game at 0.55, which over-deferred elites and pushed deep-
    bench picks to the top. Linear is gentler and respects tier demand.

    expected_remaining_after — E[games this player can still be picked in,
                             AFTER this candidate slot].
    tier_demand_factor     — pool scarcity multiplier (1.0 baseline, >1 when
                             the tier is thin so we reserve more).
    """
    if expected_utility <= 0 or expected_remaining_after <= 0:
        return 0.0
    fraction = (
        OPP_COST_PER_FUTURE_GAME * expected_remaining_after * tier_demand_factor
    )
    return min(MAX_RESERVATION_PENALTY, fraction)


def tier_demand_factor(
    priority: int | None, remaining_in_tier: int, expected_picks_left: float
) -> float:
    """How urgently we should preserve a tier slot (1.0 = baseline).

    Tighter when remaining_in_tier << expected_picks_left × tier_share.
    Returns >1.0 when scarce, <1.0 when abundant.
    """
    if not priority or expected_picks_left <= 0:
        return 1.0
    # Each tier should cover ~1/3 of remaining picks as a rough baseline.
    target = expected_picks_left / 3.0
    if remaining_in_tier <= 0:
        return 0.0  # nothing left to save in this tier; no opportunity cost
    return min(2.0, max(0.5, target / remaining_in_tier))


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


def estimate_remaining_game_days(
    active_series: list[dict],
    current_round: int,
    forecasts: dict[int, dict] | None = None,
) -> int:
    """Estimate remaining playoff game days for strategy planning.

    Blends the unbiased estimator (midway between min and max games left)
    with the user's `expected_games` forecast (same 60/40 fade rule).
    """
    forecasts = forecasts or {}
    remaining = 0.0
    for series in active_series:
        hw = series["home_wins"] or 0
        aw = series["away_wins"] or 0
        max_wins = max(hw, aw)
        played = hw + aw
        min_left = 4 - max_wins
        max_left = 7 - played
        neutral = (min_left + max_left) / 2

        fc = forecasts.get(series.get("id")) if forecasts else None
        if fc and fc.get("expected_games"):
            user_left = fc["expected_games"] - played
            user_left = max(min_left, min(max_left, user_left))
            w = _forecast_weight(played)
            est = (1 - w) * neutral + w * user_left
        else:
            est = neutral

        remaining += max(0, est)
    future_rounds = 4 - current_round
    remaining += future_rounds * 6
    game_days = int(remaining * 0.7)
    return max(1, game_days)


def elimination_risk(series_score: tuple[int, int], player_is_home: bool) -> str:
    """Assess elimination risk for a player's team going into tonight's game.

    Args:
        series_score: (home_wins, away_wins) of the player's team's series
        player_is_home: True if the player's team is the home team in that series

    Returns:
        "critical"  — team loses tonight and they're eliminated (3 losses already)
        "high"      — team is one loss away after tonight if they lose
        "none"      — no elimination pressure
    """
    hw, aw = series_score
    player_wins = hw if player_is_home else aw
    opponent_wins = aw if player_is_home else hw

    # Team already has 3 losses → a loss tonight ends their playoffs
    if opponent_wins == 3:
        return "critical"
    # Team at 2 losses → loss tonight means next loss eliminates them
    if opponent_wins == 2 and player_wins <= opponent_wins:
        return "high"
    return "none"


def should_burn_elite(
    tonight_score: float, best_future_score: float,
    elites_remaining: int, game_days_remaining: int,
    elimination: str = "none",
) -> bool:
    # Critical elimination risk: burn now or lose the player forever
    if elimination == "critical":
        return True

    if best_future_score > tonight_score * (1 + BURN_THRESHOLD):
        return False
    if elites_remaining <= 2 and game_days_remaining > 10:
        return tonight_score >= best_future_score
    return True


def compute_strategy_adjustment(
    perf_score: float, tier: str, is_home: bool,
    series_score: tuple[int, int],
    elites_remaining: int, game_days_remaining: int,
    elimination: str = "none",
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

    # Elimination-risk urgency boost (must-play tonight or lose them forever)
    if elimination == "critical":
        adjustment += 0.15
    elif elimination == "high":
        adjustment += 0.05

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
