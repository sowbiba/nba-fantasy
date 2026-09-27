"""Affectation joueurs × soirées sur l'horizon (S2) et soirée x2 du mois (S3).

Horizon = 30 jours = une fenêtre de cooldown (J+30) : « chaque joueur au
plus une fois » est exactement la règle R3. Le problème (affectation +
choix du x2 mensuel) est résolu d'un bloc par programmation linéaire en
nombres entiers (scipy.optimize.milp / HiGHS). Sans mois x2, c'est la même
affectation qu'avant (optimum de linear_sum_assignment) : maximiser la
valeur totale, un joueur pouvant rester non assigné.

Les soirées marquées « required » (le soir même) doivent être assignées si
un candidat existe, même à valeur négative : contrainte dure (et non plus
un bonus de 1e6 dans l'objectif, qui fausserait l'optimum avec l'écart
relatif toléré par le solveur).
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_array

from engine.stats.projection import GameContext

log = logging.getLogger(__name__)

TOP_PER_NIGHT = 40          # candidats gardés par soirée (modèle gérable)


@dataclass(frozen=True)
class Cell:
    player_id: int
    night: date
    projection: float
    p_play: float
    value: float
    ctx: GameContext
    x2_gain: float = 0.0    # gain attendu si ce pick est doublé (S3)


@dataclass(frozen=True)
class PlanEntry:
    cell: Cell
    is_x2: bool


def _kept_cells(cells: list[Cell], nights: list[date]) -> list[Cell]:
    wanted = set(nights)
    best: dict[tuple[int, date], Cell] = {}
    for c in cells:
        key = (c.player_id, c.night)
        if c.night in wanted and (key not in best or c.value > best[key].value):
            best[key] = c
    by_night: dict[date, list[Cell]] = defaultdict(list)
    for c in best.values():
        by_night[c.night].append(c)
    return [c for night_cells in by_night.values()
            for c in sorted(night_cells, key=lambda c: c.value, reverse=True)[:TOP_PER_NIGHT]]


def _month(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _solve_milp(kept: list[Cell], required: set[date], x2_months: dict[tuple[int, int], bool],
                x2_nights: frozenset[date] | set[date] | None):
    """Variables : x[i] (cellule i retenue) puis z[j] (cellule x2_idx[j]
    retenue ET doublée), seulement pour les cellules éligibles au x2."""
    n = len(kept)
    x2_idx = [i for i, c in enumerate(kept)
              if _month(c.night) in x2_months and (x2_nights is None or c.night in x2_nights)]
    m = len(x2_idx)
    obj = np.empty(n + m)
    obj[:n] = [-c.value for c in kept]
    obj[n:] = [-kept[i].x2_gain for i in x2_idx]

    r_idx: list[int] = []
    c_idx: list[int] = []
    vals: list[float] = []
    lo: list[float] = []
    hi: list[float] = []

    def add(cols, coefs, low, high):
        row = len(lo)
        r_idx.extend([row] * len(cols))
        c_idx.extend(cols)
        vals.extend(coefs)
        lo.append(low)
        hi.append(high)

    by_player: dict[int, list[int]] = defaultdict(list)
    by_night: dict[date, list[int]] = defaultdict(list)
    for i, c in enumerate(kept):
        by_player[c.player_id].append(i)
        by_night[c.night].append(i)
    for idx in by_player.values():
        if len(idx) > 1:
            add(idx, [1.0] * len(idx), 0, 1)
    for night, idx in by_night.items():
        add(idx, [1.0] * len(idx), 1 if night in required else 0, 1)
    by_month: dict[tuple[int, int], list[int]] = defaultdict(list)
    for j, i in enumerate(x2_idx):
        add([n + j, i], [1.0, -1.0], -np.inf, 0)                   # z ≤ x
        by_month[_month(kept[i].night)].append(n + j)
    for month, cols in by_month.items():
        add(cols, [1.0] * len(cols), 1 if x2_months[month] else 0, 1)

    a = csr_array((vals, (r_idx, c_idx)), shape=(len(lo), n + m))
    res = milp(c=obj, constraints=LinearConstraint(a, lo, hi), integrality=np.ones(n + m),
               bounds=Bounds(0, 1), options={"mip_rel_gap": 0})
    return res, x2_idx


def solve(
    cells: list[Cell],
    nights: list[date],
    required: frozenset[date] | set[date] = frozenset(),
    x2_months: dict[tuple[int, int], bool] | None = None,
    x2_nights: frozenset[date] | set[date] | None = None,
) -> dict[date, PlanEntry]:
    """Affectation joueurs × soirées (chaque joueur au plus une fois = R3 sur
    30 j, chaque soirée au plus un joueur) et soirée x2 de chaque mois (S3).

    `x2_months[(année, mois)] = forcé` : mois où un x2 est encore disponible
    (absents = pas de x2) ; forcé = le x2 doit être posé dans l'horizon.
    `x2_nights` (optionnel) restreint le x2 à ces soirées (R10 : saison
    régulière seulement) ; None = toutes les soirées des mois listés.
    Si le modèle est infaisable à cause des mois forcés, il est relancé une
    fois sans forcer (journalisé)."""
    x2_months = dict(x2_months or {})
    kept = _kept_cells(cells, nights)
    if not kept:
        return {}
    req = set(required)
    res, x2_idx = _solve_milp(kept, req, x2_months, x2_nights)
    if (res.status != 0 or res.x is None) and any(x2_months.values()):
        log.warning("planificateur : x2 forcé infaisable (%s), relance sans forcer", res.message)
        x2_months = dict.fromkeys(x2_months, False)
        res, x2_idx = _solve_milp(kept, req, x2_months, x2_nights)
    if res.status != 0 or res.x is None:
        raise RuntimeError(f"planificateur : pas de solution ({res.message})")
    n = len(kept)
    doubled = {i for j, i in enumerate(x2_idx) if res.x[n + j] > 0.5}
    plan = {kept[i].night: PlanEntry(kept[i], i in doubled) for i in range(n) if res.x[i] > 0.5}
    return dict(sorted(plan.items()))
