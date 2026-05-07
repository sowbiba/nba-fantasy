"""Personal-strategy multiplier on estimated_score.

Translates the user's bracket view (per-team outlook + per-player save
rank) into a multiplier that sits next to play_probability and
dnp_risk_factor in main.py:

    estimated_score *= personal_multiplier

The function is intentionally pure so it's trivially testable and the
caller in main.py just wires the inputs.

The three outlooks:

  - "advance"   : team expected to go deep. Save the top-ranked players
                  (1, 2, sometimes 3). Penalty auto-releases when the
                  team faces real elimination pressure.

  - "eliminate" : team expected to lose this round. Use everyone before
                  they're gone. Top-ranked players get a mild
                  away-penalty so we wait for a home game to play them.

  - "tossup"    : balanced series. Slight save on the (1)/(2) and a
                  slight boost on the mid-list (rank 3-4) — matches the
                  user's "milieu de liste" instinct when the bracket is
                  uncertain.

Two override channels keep the static ranking from being too rigid:

  - Hot streak  : when a player is on fire, half the save penalty melts.
                  A surprise 50 TTFL average over the last 5 should not
                  be hidden behind a "save him for finals" tax.

  - Elimination : 'high' and 'critical' release the save penalty
                  entirely (you're about to lose the player forever).
"""
from dataclasses import dataclass


# Save penalties for outlook='advance'. Below 1.0 = de-prioritized so
# the engine prefers a different candidate at equal floor.
ADVANCE_PENALTY = {1: 0.40, 2: 0.60, 3: 0.80}

# Tossup curve: slight save on top, mid-list nudge.
TOSSUP_CURVE = {1: 0.85, 2: 0.90, 3: 1.05, 4: 1.05}

# Eliminated team: home/away preference for top-ranked picks.
ELIMINATE_TOP_HOME_BOOST = 1.10
ELIMINATE_TOP_AWAY_PENALTY = 0.90
# A "top" rank for the home/away nudge means rank 1 or 2.
ELIMINATE_TOP_RANK_THRESHOLD = 2

# When a player is hot (avg_l5 > season_avg * HOT_THRESHOLD) we move any
# multiplier halfway back towards 1.0. This means a 0.40 save penalty
# becomes 0.70 — still a save signal, but not enough to bury a player
# who's clearly riding a wave.
HOT_THRESHOLD = 1.20


@dataclass
class PersonalContext:
    """Inputs needed to compute the personal-strategy multiplier."""
    save_rank: int | None  # None = player not in player_team_rank table
    team_outlook: str | None  # None = no outlook recorded for the team
    home_save_top: bool
    is_home_game: bool
    elimination_risk: str  # "none" | "high" | "critical"
    avg_l5: float
    season_avg: float


def is_hot(avg_l5: float, season_avg: float) -> bool:
    """Player on a hot streak = recent form clearly above season baseline."""
    if season_avg <= 0:
        return False
    return avg_l5 > season_avg * HOT_THRESHOLD


def _apply_hot_relief(multiplier: float, hot: bool) -> float:
    """Move a save penalty halfway back towards 1.0 when the player is hot.

    Boosts (>1.0) are left alone — being hot shouldn't double the bump.
    """
    if not hot or multiplier >= 1.0:
        return multiplier
    return multiplier + (1.0 - multiplier) * 0.5


def compute_multiplier(ctx: PersonalContext) -> tuple[float, str]:
    """Return (multiplier, reason_tag) for the given context.

    Multiplier is clamped to [0.40, 1.30]. The reason tag is short and
    machine-friendly so the advisor layer can map it to a French line.
    """
    # Elimination always wins: if you might never see this player again,
    # all save logic is moot.
    if ctx.elimination_risk == "critical":
        return 1.20, "elim_critical_release"
    if ctx.elimination_risk == "high":
        return 1.05, "elim_high_release"

    # No outlook recorded → engine treats the player as neutral.
    if not ctx.team_outlook:
        return 1.0, "no_outlook"

    # No rank recorded → can't apply the per-player curve. Outlook alone
    # doesn't tell us whether this specific player should be saved.
    if ctx.save_rank is None:
        return 1.0, "no_rank"

    hot = is_hot(ctx.avg_l5, ctx.season_avg)

    if ctx.team_outlook == "advance":
        base = ADVANCE_PENALTY.get(ctx.save_rank, 1.0)
        multiplier = _apply_hot_relief(base, hot)
        if multiplier < 1.0:
            tag = f"save_advance_r{ctx.save_rank}"
            if hot:
                tag += "_hot"
            return _clamp(multiplier), tag
        return _clamp(multiplier), "burn_advance"

    if ctx.team_outlook == "tossup":
        base = TOSSUP_CURVE.get(ctx.save_rank, 0.95)
        multiplier = _apply_hot_relief(base, hot)
        if base < 1.0:
            tag = f"tossup_save_r{ctx.save_rank}"
        elif base > 1.0:
            tag = f"tossup_midlist_r{ctx.save_rank}"
        else:
            tag = "tossup_neutral"
        if hot and base < 1.0:
            tag += "_hot"
        return _clamp(multiplier), tag

    if ctx.team_outlook == "eliminate":
        # No save penalty — we want to use these players. Only the
        # home/away nudge applies, and only to top-ranked players when
        # the user opted into home_save_top.
        if not ctx.home_save_top:
            return 1.0, "burn_eliminate"
        if ctx.save_rank > ELIMINATE_TOP_RANK_THRESHOLD:
            return 1.0, "burn_eliminate"
        if ctx.is_home_game:
            return _clamp(ELIMINATE_TOP_HOME_BOOST), f"eliminate_home_r{ctx.save_rank}"
        # Away game and top-ranked: gentle nudge to wait for a home game.
        # Hot relief still applies — a hot player doesn't deserve to wait.
        multiplier = _apply_hot_relief(ELIMINATE_TOP_AWAY_PENALTY, hot)
        tag = f"eliminate_away_r{ctx.save_rank}"
        if hot:
            tag += "_hot"
        return _clamp(multiplier), tag

    # Unknown outlook string — treat as neutral rather than crashing.
    return 1.0, "unknown_outlook"


def _clamp(value: float) -> float:
    return max(0.40, min(1.30, value))
