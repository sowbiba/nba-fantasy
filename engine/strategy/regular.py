"""Décision du soir et plan 30 jours (S1, S2, S3 : soirée x2 du mois).

Reco du soir (L1) = best-available trié par valeur S1. Le plan est indicatif
jusqu'à sa validation par backtest (L2, règle d'activation de la spec §7,
voir engine.strategy.config.TONIGHT_SOURCE).
Les règles de disponibilité viennent de engine.rules : en PO, le même
calcul applique automatiquement le pick-and-drop et les éliminations (la
stratégie PO dédiée arrive en L3).
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from engine.rules.availability import COOLDOWN_DAYS, PickRow, SecondChance, SeriesRow, is_available
from engine.rules.calendar import Night
from engine.rules.game_types import is_eligible
from engine.stats.availability_prob import HARD_OUT_STATUSES, future_p_play, p_play
from engine.stats.profile import PlayerProfile
from engine.stats.projection import GameContext, project, rest_days
from engine.stats.team_defense import opp_factor
from engine.strategy.config import TONIGHT_SOURCE
from engine.strategy.planner import Cell, PlanEntry, solve
from engine.strategy.value import X2_MONTHS, future_value, lock_value, tonight_value, x2_gain

log = logging.getLogger(__name__)

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
    x2_used_months: frozenset[tuple[int, int]] = frozenset()   # mois où un pick is_x2 existe déjà


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
    plan: dict[date, PlanEntry]


def _game_date(g: dict) -> date:
    d = g["date"]
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def _is_phantom(game: dict, completed_pairs: set[tuple[str, frozenset[str]]]) -> bool:
    """R13 (jobs) : un match de PO programmé dont la série est déjà terminée
    la même saison n'a jamais lieu. Sans clé "status" (matchs historiques /
    régulière), ou sans "season", jamais considéré fantôme."""
    if game.get("game_type") != "playoffs" or game.get("status") != "scheduled":
        return False
    season = game.get("season")
    if season is None:
        return False
    pair = frozenset({game["home_team"], game["away_team"]})
    return (season, pair) in completed_pairs


def _x2_months(inputs: DecisionInputs, horizon: dict[date, Night]) -> dict[tuple[int, int], bool]:
    """S3/R10 : mois (année, mois) de l'horizon où un x2 est encore
    disponible (novembre–avril, saison régulière, pas déjà utilisé) → forcé
    si la dernière soirée SR éligible du mois dans `inputs.nights` tombe dans
    l'horizon. Suppose que `inputs.nights` couvre au-delà de l'horizon
    (daily_sync charge 35 j) : sinon un mois serait forcé à tort."""
    if not horizon:
        return {}
    last_in_horizon = max(horizon)
    last_of_month: dict[tuple[int, int], date] = {}
    for n in inputs.nights:
        if n.is_phantom or n.n_eligible_games <= 0 or n.mode != "regular":
            continue
        key = (n.date.year, n.date.month)
        last_of_month[key] = max(last_of_month.get(key, n.date), n.date)
    months = {(d.year, d.month) for d, n in horizon.items() if n.mode == "regular"}
    return {m: last_of_month[m] <= last_in_horizon for m in sorted(months)
            if m[1] in X2_MONTHS and m not in inputs.x2_used_months}


def _picked_cells(inputs: DecisionInputs, nights: dict[date, Night],
                  x2_months: dict[tuple[int, int], bool], games_by_night: dict[date, list[dict]],
                  estimate, decay: float | None) -> dict[date, Cell]:
    """Cellule planificateur du joueur pické, pour chaque soirée déjà pickée
    de l'horizon en saison régulière dans un mois où le x2 est encore
    disponible (`x2_months`). Calculée comme les autres cellules (projection,
    p_play, valeur, gain x2) mais sans le filtre de disponibilité : le
    cooldown de son propre pick l'exclurait. Soirée ignorée si le joueur n'a
    pas de profil ou pas de match éligible ce soir-là."""
    latest: dict[date, PickRow] = {}
    for p in inputs.picks:
        if p.date not in latest or p.id > latest[p.date].id:
            latest[p.date] = p
    out: dict[date, Cell] = {}
    for d, pick in latest.items():
        night = nights.get(d)
        if night is None or night.mode != "regular" or (d.year, d.month) not in x2_months:
            continue
        row = inputs.players.get(pick.player_id)
        if row is None or inputs.profiles.get(pick.player_id) is None:
            continue
        team = row["team"]
        game = next((g for g in games_by_night[d] if team in (g["home_team"], g["away_team"])), None)
        if game is None:
            continue
        is_home = game["home_team"] == team
        opponent = game["away_team"] if is_home else game["home_team"]
        k = (d - inputs.today).days
        projection, p, ctx = estimate(pick.player_id, team, opponent, is_home, d, k)
        out[d] = Cell(pick.player_id, d, projection, p, future_value(k, p, projection, decay), ctx,
                      x2_gain=x2_gain(p, projection, inputs.profiles[pick.player_id].stddev))
    return out


def decide(inputs: DecisionInputs, tonight_source: str = TONIGHT_SOURCE, decay: float | None = None) -> Decision:
    today = inputs.today
    nights = {n.date: n for n in inputs.nights
              if not n.is_phantom and n.n_eligible_games > 0 and 0 <= (n.date - today).days < HORIZON_DAYS}

    completed_pairs = {(s.season, frozenset({s.home_team, s.away_team}))
                        for s in inputs.series if s.status == "completed"}

    team_dates: dict[str, list[date]] = defaultdict(list)
    games_by_night: dict[date, list[dict]] = defaultdict(list)
    for g in inputs.games:
        if _is_phantom(g, completed_pairs):
            continue
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

    def _estimate(pid: int, team: str, opponent: str, is_home: bool, d: date, k: int
                  ) -> tuple[float, float, GameContext]:
        """(projection, p_play, contexte) d'un joueur sur un match (S1)."""
        profile = inputs.profiles[pid]
        row = inputs.players[pid]
        status = row.get("injury_status")
        rd = rest_days(team, d, team_dates)
        ctx = GameContext(opponent, is_home, rd, opp_factor(inputs.defense, opponent, row.get("position", "F")))
        projection = project(profile, ctx)
        b2b = rd == 0
        if k == 0:
            p = p_play(injury_status=status, recent_logs=inputs.recent_logs.get(pid, []),
                       is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
        else:
            p = future_p_play(injury_status=status, availability_rate=profile.availability_rate,
                              is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
        return projection, p, ctx

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
                    raw.append((k, pid, d, *_estimate(pid, team, opponent, is_home, d, k)))

    # Dédoublonnage par (joueur, soirée) : une ligne de match dupliquée ne
    # doit produire qu'une seule cellule, celle de plus forte espérance
    # (p × projection, proportionnelle à la valeur qui en découlera).
    deduped: dict[tuple[int, date], tuple[int, int, date, float, float, GameContext]] = {}
    for entry in raw:
        _k, pid, d, projection, p, _ctx = entry
        key = (pid, d)
        existing = deduped.get(key)
        if existing is None or p * projection > existing[4] * existing[3]:
            deduped[key] = entry
    raw = list(deduped.values())

    future_ev: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for k, pid, _d, projection, p, _ctx in raw:
        if k > 0:
            future_ev[pid].append((k, p * projection))

    # Les cellules "recommandations" portent le coût du blocage de 30 j
    # (tonight_value) ; celles données au planificateur ne doivent pas le
    # compter une seconde fois, car l'affectation elle-même immobilise déjà
    # le joueur (une soirée = un joueur au plus une fois, R3).
    cells: list[Cell] = []
    planner_cells: list[Cell] = []
    for k, pid, d, projection, p, ctx in raw:
        if k == 0:
            reco_value = tonight_value(p, projection, lock_value(future_ev[pid], decay))
            plan_value = future_value(0, p, projection, decay)
        else:
            reco_value = plan_value = future_value(k, p, projection, decay)
        cell = Cell(pid, d, projection, p, reco_value, ctx)
        cells.append(cell)
        gain = x2_gain(p, projection, inputs.profiles[pid].stddev) if nights[d].mode == "regular" else 0.0
        planner_cells.append(replace(cell, value=plan_value, x2_gain=gain))

    x2_months = _x2_months(inputs, nights)
    fixed = {p.date for p in inputs.picks}
    free_nights = {d for d in nights if d not in fixed}
    # Soirées déjà pickées (réservations, pick du soir) dans un mois x2
    # ouvert : gardées dans le modèle avec une seule cellule, le joueur de
    # l'utilisateur, assignée d'office — le x2 peut ainsi se poser sur son
    # pick, et un mois forcé garde sa variable sur sa dernière soirée (I-2).
    forced_cells = _picked_cells(inputs, nights, x2_months, games_by_night, _estimate, decay)
    plan_nights = sorted(free_nights | set(forced_cells))
    required = set(forced_cells) | ({today} if today in free_nights else set())
    try:
        plan = solve([c for c in planner_cells if c.night in free_nights] + list(forced_cells.values()),
                     plan_nights, required=required, x2_months=x2_months,
                     x2_nights={d for d in plan_nights if nights[d].mode == "regular"})
    except RuntimeError:
        # Le plan est indicatif : son échec ne doit jamais priver la soirée
        # de ses recommandations (écrites par daily_sync juste après).
        log.exception("planificateur en échec : plan vide, recommandations conservées")
        plan = {}

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
                cell=c, lock_value=lock_value(future_ev[c.player_id], decay),
                locked_until=today + timedelta(days=COOLDOWN_DAYS), best_future=best))

        if tonight_source == "plan":
            plan_entry = plan.get(today)
            if plan_entry is not None:
                plan_pid = plan_entry.cell.player_id
                idx = next((i for i, r in enumerate(recommendations) if r.cell.player_id == plan_pid), None)
                if idx is not None:
                    recommendations.insert(0, recommendations.pop(idx))
                else:
                    # Filtré hors du top (TOP_RECOMMENDATIONS) : reconstruire sa
                    # recommandation (même cellule S1 que les autres recos).
                    reco_cell = next((c for c in tonight_cells if c.player_id == plan_pid), None)
                    if reco_cell is not None:
                        best = max(future_cells[plan_pid], key=lambda f: f.value, default=None)
                        recommendations.insert(0, Recommendation(
                            cell=reco_cell, lock_value=lock_value(future_ev[plan_pid], decay),
                            locked_until=today + timedelta(days=COOLDOWN_DAYS), best_future=best))
                        del recommendations[TOP_RECOMMENDATIONS:]
    return Decision(tonight, recommendations, plan)
