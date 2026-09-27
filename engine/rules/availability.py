"""R3, R4, R5, R6, R15 — disponibilité d'un joueur pour une soirée.

Miroir exact de la fonction SQL player_available_on (migration 018) : les
deux implémentations rejouent tests/rules/availability_cases.json.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

COOLDOWN_DAYS = 30       # R3 : pické le jour J → disponible à J+30
SECOND_CHANCE_DAYS = 7   # R15 : repick dans les 7 jours suivant l'achat


@dataclass(frozen=True)
class PickRow:
    id: int
    player_id: int
    date: date
    mode: str    # 'regular' | 'playoffs'
    season: str
    is_x2: bool = False


@dataclass(frozen=True)
class SecondChance:
    pick_id: int   # le pick à 0 que le bonus débloque
    player_id: int
    bought_on: date
    expires_on: date


@dataclass(frozen=True)
class SeriesRow:
    season: str
    round: int
    home_team: str
    away_team: str
    home_wins: int
    away_wins: int
    status: str


@dataclass(frozen=True)
class Availability:
    ok: bool
    available_from: date | None = None
    reason: str | None = None


AVAILABLE = Availability(True)


def is_available(
    *,
    player_id: int,
    player_team: str,
    night: date,
    season: str,
    mode: str,
    picks: Iterable[PickRow],
    second_chances: Iterable[SecondChance] = (),
    series: Iterable[SeriesRow] = (),
    exclude_pick_id: int | None = None,
) -> Availability:
    """Le joueur peut-il être pické (ou réservé) pour `night` ?

    Seuls comptent les picks du joueur dans la même saison et le même mode
    (R6 : les picks de SR ne comptent plus en PO). `exclude_pick_id` écarte
    la ligne en cours de remplacement (R2).
    """
    own = [
        p for p in picks
        if p.player_id == player_id and p.season == season
        and p.mode == mode and p.id != exclude_pick_id
    ]
    if mode == "playoffs":
        return _playoffs(own, player_team, season, list(series))
    return _regular(own, night, second_chances)


def _regular(own: list[PickRow], night: date, second_chances: Iterable[SecondChance]) -> Availability:
    unlocked = {sc.pick_id for sc in second_chances if sc.bought_on <= night <= sc.expires_on}
    blocking = [
        p for p in own
        if p.id not in unlocked and abs((night - p.date).days) < COOLDOWN_DAYS
    ]
    before = [p.date for p in blocking if p.date <= night]
    if before:
        return Availability(False, max(before) + timedelta(days=COOLDOWN_DAYS), "cooldown")
    if blocking:
        return Availability(False, None, "reserved_nearby")
    return AVAILABLE


def _playoffs(own: list[PickRow], team: str, season: str, series: list[SeriesRow]) -> Availability:
    if own:
        return Availability(False, None, "playoffs_used")
    this_season = [s for s in series if s.season == season]
    first_round = [s for s in this_season if s.round == 1]
    if first_round and not any(team in (s.home_team, s.away_team) for s in first_round):
        return Availability(False, None, "not_qualified")
    for s in this_season:
        lost_home = s.home_team == team and s.home_wins < 4
        lost_away = s.away_team == team and s.away_wins < 4
        if s.status == "completed" and (lost_home or lost_away):
            return Availability(False, None, "team_eliminated")
    return AVAILABLE
