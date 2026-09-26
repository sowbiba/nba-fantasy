"""Affectation joueurs × soirées sur l'horizon (S2).

Horizon = 30 jours = une fenêtre de cooldown (J+30) : « chaque joueur au
plus une fois » est exactement la règle R3. Problème d'affectation résolu
par linear_sum_assignment (algorithme hongrois) avec colonnes fictives pour
permettre aux joueurs de rester non assignés (objectif : maximiser la valeur
totale, pas le nombre d'assignations). Les soirées marquées « required »
doivent être assignées si un candidat existe, même à valeur négative.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import linear_sum_assignment

from engine.stats.projection import GameContext

TOP_PER_NIGHT = 40          # candidats gardés par soirée (matrice gérable)
_SENTINEL = 1e9             # coût d'une case impossible
_REQUIRED_BONUS = 1e6       # bonus pour forcer l'assignation des soirées obligatoires


@dataclass(frozen=True)
class Cell:
    player_id: int
    night: date
    projection: float
    p_play: float
    value: float
    ctx: GameContext


def solve(
    cells: list[Cell],
    nights: list[date],
    required: frozenset[date] | set[date] = frozenset(),
) -> dict[date, Cell]:
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
    # Matrice : len(players) lignes × (len(nights) + len(players)) colonnes
    # Premières len(nights) colonnes : soirées réelles
    # Dernières len(players) colonnes : colonnes fictives "pas de pick"
    cost = np.full((len(players), len(nights) + len(players)), _SENTINEL)
    # Remplir les colonnes fictives avec coût 0 (joueur non utilisé)
    for i in range(len(players)):
        cost[i, len(nights) + i] = 0
    best: dict[tuple[int, date], Cell] = {}
    for c in kept:
        key = (c.player_id, c.night)
        if key not in best or c.value > best[key].value:
            best[key] = c
            j = col[c.night]
            if c.night in required:
                # Bonus pour forcer l'assignation des soirées obligatoires
                cost[row[c.player_id], j] = -c.value - _REQUIRED_BONUS
            else:
                cost[row[c.player_id], j] = -c.value
    rows, cols = linear_sum_assignment(cost)
    plan = {}
    for r, j in zip(rows, cols):
        # Garder uniquement les assignations aux colonnes réelles (< len(nights))
        # et dont le coût n'est pas le sentinel
        if j < len(nights) and cost[r, j] < _SENTINEL:
            plan[nights[j]] = best[(players[r], nights[j])]
    return dict(sorted(plan.items()))
