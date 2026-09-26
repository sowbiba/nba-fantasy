"""Décision du soir et plan 30 jours (S1, S2).

Reco du soir (L1) = best-available trié par valeur S1. Le plan est indicatif
jusqu'à sa validation par backtest (L2, règle d'activation de la spec §7).
Les règles de disponibilité viennent de engine.rules : en PO, le même
calcul applique automatiquement le pick-and-drop et les éliminations (la
stratégie PO dédiée arrive en L3).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.rules.availability import COOLDOWN_DAYS, PickRow, SecondChance, SeriesRow, is_available
from engine.rules.calendar import Night
from engine.rules.game_types import is_eligible
from engine.stats.availability_prob import HARD_OUT_STATUSES, future_p_play, p_play
from engine.stats.profile import PlayerProfile
from engine.stats.projection import GameContext, project, rest_days
from engine.stats.team_defense import opp_factor
from engine.strategy.planner import Cell, solve
from engine.strategy.value import future_value, lock_value, tonight_value

HORIZON_DAYS = 30
MIN_EXP_MINUTES = 15.0
TOP_RECOMMENDATIONS = 50


@dataclass
class DecisionInputs:
    today: date
    nights: list[Night]
    games: list[dict]
    players: dict[int, dict]
    profiles: dict[int, PlayerProfile]
    recent_logs: dict[int, list[dict]]
    defense: dict[str, dict[str, float]]
    picks: list[PickRow]
    second_chances: list[SecondChance] = field(default_factory=list)
    series: list[SeriesRow] = field(default_factory=list)


@dataclass(frozen=True)
class Recommendation:
    cell: Cell
    lock_value: float
    locked_until: date
    best_future: Cell | None


@dataclass
class Decision:
    tonight: date | None
    recommendations: list[Recommendation]
    plan: dict[date, Cell]


def _game_date(g: dict) -> date:
    d = g["date"]
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def decide(inputs: DecisionInputs) -> Decision:
    today = inputs.today
    nights = {n.date: n for n in inputs.nights
              if not n.is_phantom and n.n_eligible_games > 0 and 0 <= (n.date - today).days < HORIZON_DAYS}

    team_dates: dict[str, list[date]] = defaultdict(list)
    games_by_night: dict[date, list[dict]] = defaultdict(list)
    for g in inputs.games:
        d = _game_date(g)
        team_dates[g["home_team"]].append(d)
        team_dates[g["away_team"]].append(d)
        if d in nights and is_eligible(g.get("game_type", "unknown")):
            games_by_night[d].append(g)
    for dates in team_dates.values():
        dates.sort()

    roster: dict[str, list[int]] = defaultdict(list)
    for pid, row in inputs.players.items():
        if row.get("active", True):
            roster[row["team"]].append(pid)

    raw = []  # (days_ahead, player_id, night, projection, p, ctx)
    for d, night in nights.items():
        k = (d - today).days
        for g in games_by_night[d]:
            for team, opponent, is_home in ((g["home_team"], g["away_team"], True),
                                            (g["away_team"], g["home_team"], False)):
                for pid in roster.get(team, []):
                    profile = inputs.profiles.get(pid)
                    if profile is None or profile.exp_minutes < MIN_EXP_MINUTES:
                        continue
                    row = inputs.players[pid]
                    status = row.get("injury_status")
                    if k == 0 and status in HARD_OUT_STATUSES:
                        continue
                    if not is_available(player_id=pid, player_team=team, night=d, season=night.season,
                                        mode=night.mode, picks=inputs.picks,
                                        second_chances=inputs.second_chances, series=inputs.series).ok:
                        continue
                    rd = rest_days(team, d, team_dates)
                    ctx = GameContext(opponent, is_home, rd,
                                      opp_factor(inputs.defense, opponent, row.get("position", "F")))
                    projection = project(profile, ctx)
                    b2b = rd == 0
                    if k == 0:
                        p = p_play(injury_status=status, recent_logs=inputs.recent_logs.get(pid, []),
                                   is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
                    else:
                        p = future_p_play(injury_status=status, availability_rate=profile.availability_rate,
                                          is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
                    raw.append((k, pid, d, projection, p, ctx))

    future_ev: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for k, pid, _d, projection, p, _ctx in raw:
        if k > 0:
            future_ev[pid].append((k, p * projection))

    cells: list[Cell] = []
    for k, pid, d, projection, p, ctx in raw:
        if k == 0:
            value = tonight_value(p, projection, lock_value(future_ev[pid]))
        else:
            value = future_value(k, p, projection)
        cells.append(Cell(pid, d, projection, p, value, ctx))

    fixed = {p.date for p in inputs.picks}
    plan_nights = sorted(d for d in nights if d not in fixed)
    plan = solve([c for c in cells if c.night in set(plan_nights)], plan_nights,
                 required={today} if today in plan_nights else frozenset())

    tonight = today if today in nights else None
    recommendations: list[Recommendation] = []
    if tonight is not None:
        future_cells: dict[int, list[Cell]] = defaultdict(list)
        for c in cells:
            if c.night != today:
                future_cells[c.player_id].append(c)
        tonight_cells = sorted((c for c in cells if c.night == today), key=lambda c: c.value, reverse=True)
        for c in tonight_cells[:TOP_RECOMMENDATIONS]:
            best = max(future_cells[c.player_id], key=lambda f: f.value, default=None)
            recommendations.append(Recommendation(
                cell=c, lock_value=lock_value(future_ev[c.player_id]),
                locked_until=today + timedelta(days=COOLDOWN_DAYS), best_future=best))
    return Decision(tonight, recommendations, plan)
