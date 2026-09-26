"""R8 (fermeture du deck), R11 (soirées éligibles), R13 (match fantôme).

Une soirée TTFL = une date US ayant au moins un match éligible non fantôme.
Les soirées ne contenant que des matchs fantômes sont gardées avec
is_phantom=True, pour alerter si une réservation y est posée (R13).
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from engine.rules.game_types import is_eligible, mode_of

PARIS = ZoneInfo("Europe/Paris")


def closing_at(night: date, tip_offs: Iterable[datetime | None]) -> datetime:
    """R8 : 00:00 heure de Paris à la fin de la soirée, ou le premier
    tip-off s'il est plus tôt. Retourne un datetime aware en Europe/Paris."""
    midnight = datetime.combine(night + timedelta(days=1), time(0, 0), tzinfo=PARIS)
    tips = [t.astimezone(PARIS) for t in tip_offs if t is not None]
    return min([midnight, *tips])


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def is_phantom(game: dict, completed_series: list[dict]) -> bool:
    """R13 : match de PO programmé d'une série déjà terminée, la même saison.
    Lien par series_id ou, à défaut, par paire d'équipes (les matchs
    conditionnels perdent parfois leur lien de série)."""
    if game.get("game_type") != "playoffs" or game.get("status") != "scheduled":
        return False
    same_season = [s for s in completed_series if s.get("season") == game.get("season")]
    if game.get("series_id") in {s["id"] for s in same_season}:
        return True
    pairs = {_pair(s["home_team"], s["away_team"]) for s in same_season}
    return _pair(game["home_team"], game["away_team"]) in pairs


@dataclass(frozen=True)
class Night:
    date: date
    season: str
    mode: str
    n_eligible_games: int
    closing_at: datetime
    is_phantom: bool


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _as_dt(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def build_nights(games: list[dict], series: list[dict]) -> list[Night]:
    completed = [s for s in series if s.get("status") == "completed"]
    by_date: dict[date, list[dict]] = {}
    for g in games:
        if is_eligible(g.get("game_type", "unknown")):
            by_date.setdefault(_as_date(g["date"]), []).append(g)

    nights = []
    for d in sorted(by_date):
        day_games = by_date[d]
        real = [g for g in day_games if not is_phantom(g, completed)]
        reference = real or day_games
        mode = "playoffs" if any(mode_of(g["game_type"]) == "playoffs" for g in reference) else "regular"
        nights.append(Night(
            date=d,
            season=reference[0]["season"],
            mode=mode,
            n_eligible_games=len(real),
            closing_at=closing_at(d, [_as_dt(g.get("tip_off")) for g in real]),
            is_phantom=not real,
        ))
    return nights
