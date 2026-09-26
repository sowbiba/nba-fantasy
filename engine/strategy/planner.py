"""Affectation joueurs × soirées sur l'horizon (S2).

Horizon = 30 jours = une fenêtre de cooldown (J+30) : « chaque joueur au
plus une fois » est exactement la règle R3. Problème d'affectation résolu
par linear_sum_assignment (algorithme hongrois).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import linear_sum_assignment

from engine.stats.projection import GameContext

TOP_PER_NIGHT = 40          # candidats gardés par soirée (matrice gérable)
_SENTINEL = 1e9             # coût d'une case impossible


@dataclass(frozen=True)
class Cell:
    player_id: int
    night: date
    projection: float
    p_play: float
    value: float
    ctx: GameContext


def solve(cells: list[Cell], nights: list[date]) -> dict[date, Cell]:
    if not cells or not nights:
        return {}
    wanted = set(nights)
    by_night: dict[date, list[Cell]] = defaultdict(list)
    for c in cells:
        if c.night in wanted:
            by_night[c.night].append(c)
    kept = [c for night_cells in by_night.values()
            for c in sorted(night_cells, key=lambda c: c.value, reverse=True)[:TOP_PER_NIGHT]]
    if not kept:
        return {}
    players = sorted({c.player_id for c in kept})
    row = {pid: i for i, pid in enumerate(players)}
    col = {d: j for j, d in enumerate(nights)}
    cost = np.full((len(players), len(nights)), _SENTINEL)
    best: dict[tuple[int, date], Cell] = {}
    for c in kept:
        key = (c.player_id, c.night)
        if key not in best or c.value > best[key].value:
            best[key] = c
            cost[row[c.player_id], col[c.night]] = -c.value
    rows, cols = linear_sum_assignment(cost)
    plan = {}
    for r, j in zip(rows, cols):
        if cost[r, j] >= _SENTINEL:
            continue
        plan[nights[j]] = best[(players[r], nights[j])]
    return dict(sorted(plan.items()))
