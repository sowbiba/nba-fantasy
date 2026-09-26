"""Projection TTFL d'un joueur pour un match : base du profil (efficacité ×
minutes de rôle) × adversaire × terrain × fatigue.

Facteurs volontairement peu nombreux : le facteur de tendance historique
était inversé (audit §3) et redondant avec la pondération de récence du
profil ; le split domicile/extérieur individuel est remplacé par un effet
terrain fixe (split individuel trop bruité, et compté deux fois).
"""
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

from engine.stats.profile import PlayerProfile

HOME_FACTOR = 1.02
AWAY_FACTOR = 0.98
B2B_FACTOR = 0.96


@dataclass(frozen=True)
class GameContext:
    opponent: str
    is_home: bool
    rest_days: int | None
    opp_factor: float


def project(profile: PlayerProfile, ctx: GameContext) -> float:
    terrain = HOME_FACTOR if ctx.is_home else AWAY_FACTOR
    fatigue = B2B_FACTOR if ctx.rest_days == 0 else 1.0
    return profile.base * ctx.opp_factor * terrain * fatigue


def rest_days(team: str, night: date, team_dates: dict[str, list[date]]) -> int | None:
    """Jours de repos avant `night` (0 = 2e soir d'un back-to-back). None si
    aucun match antérieur connu. `team_dates` triées par date."""
    dates = team_dates.get(team, [])
    i = bisect_left(dates, night)
    if i == 0:
        return None
    return (night - dates[i - 1]).days - 1
