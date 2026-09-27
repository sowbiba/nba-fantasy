"""Facteur « écart de force » (spec `docs/superpowers/specs/2026-09-28-l3a-elo-design.md` §2).

Quand un gros écart de points est attendu, les titulaires jouent moins
(garbage time) et les remplaçants plus. Le modèle est calibré sur les logs
passés : pour chaque match joué (minutes > 0) d'un match terminé avant la
date de décision, `ratio = minutes / moyenne de minutes du joueur (même
saison)` est régressé (moindres carrés simples, avec constante) sur
`z = max(0, |écart final| − t)`, séparément pour les titulaires (moyenne ≥
28 min) et les autres. Le seuil `t` de chaque groupe est choisi dans
`THRESHOLD_GRID` (plus petite somme des carrés des résidus) ; la pente est
bornée (baisse titulaires ∈ [0 ; 0,02]/pt, hausse remplaçants ∈ [0 ; 0,03]/pt).

Application (`factor`) avec l'écart ATTENDU (Elo corrigé des absents) :
titulaire `1 − a × max(0, |écart| − t)`, remplaçant `1 + b × max(0, |écart| − t)`,
borné à [0,85 ; 1,15].

Limite connue : la pente est mesurée sur l'écart final (dispersion large)
mais appliquée à l'écart attendu (Elo : rarement plus de ~12 pts) ; avec le
même seuil, le facteur quitte peu 1,0. C'est la formule de la spec ; la
règle d'activation (backtest dans les deux modes) tranche.

Aucune fuite : seuls les logs ET les matchs de date strictement antérieure
à `before` sont utilisés.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from engine.stats.elo import as_date, is_countable
from engine.stats.profile import GameLog

STARTER_MINUTES = 28.0
MIN_GAMES_FOR_AVERAGE = 5            # moyenne de minutes trop bruitée en dessous
THRESHOLD_GRID = (0.0, 5.0, 10.0, 15.0, 20.0)
STARTER_SLOPE_BOUNDS = (0.0, 0.02)
BENCH_SLOPE_BOUNDS = (0.0, 0.03)
FACTOR_BOUNDS = (0.85, 1.15)
DEFAULT_THRESHOLD = 10.0


@dataclass(frozen=True)
class BlowoutModel:
    starter_slope: float        # baisse relative des minutes par point d'écart au-delà du seuil
    starter_threshold: float
    bench_slope: float          # hausse relative des minutes par point d'écart au-delà du seuil
    bench_threshold: float


NEUTRAL = BlowoutModel(0.0, DEFAULT_THRESHOLD, 0.0, DEFAULT_THRESHOLD)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _fit(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """(pente, seuil) des moindres carrés `ratio ~ c + pente × max(0, x − t)`,
    t choisi dans THRESHOLD_GRID par SSE minimale. None si aucun seuil
    n'offre de variance en z (pas assez de données)."""
    n = len(points)
    if n < 2:
        return None
    best: tuple[float, float, float] | None = None   # (sse, pente, seuil)
    sy = sum(r for _, r in points)
    syy = sum(r * r for _, r in points)
    for t in THRESHOLD_GRID:
        sz = szz = szy = 0.0
        for x, r in points:
            z = x - t
            if z > 0:
                sz += z
                szz += z * z
                szy += z * r
        var_z = szz - sz * sz / n
        if var_z <= 1e-12:
            continue
        cov = szy - sz * sy / n
        slope = cov / var_z
        sse = (syy - sy * sy / n) - slope * cov
        if best is None or sse < best[0] - 1e-12:
            best = (sse, slope, t)
    if best is None:
        return None
    return best[1], best[2]


def calibrate(logs: list[GameLog], games: list[dict], before: date) -> BlowoutModel:
    """Modèle calibré sur les logs et matchs terminés de date < `before`.
    Modèle neutre (pentes nulles) pour un groupe sans données exploitables."""
    margin_by_game: dict[str, float] = {}
    for g in games:
        if is_countable(g) and as_date(g["date"]) < before:
            margin_by_game[str(g.get("id"))] = abs(g["home_score"] - g["away_score"])

    played = [l for l in logs if l.date < before and l.minutes > 0]
    totals: dict[tuple[int, str], list[float]] = defaultdict(lambda: [0.0, 0])
    for l in played:
        acc = totals[(l.player_id, l.season)]
        acc[0] += l.minutes
        acc[1] += 1

    starters: list[tuple[float, float]] = []
    bench: list[tuple[float, float]] = []
    for l in played:
        margin = margin_by_game.get(l.game_id)
        if margin is None:
            continue
        total, count = totals[(l.player_id, l.season)]
        if count < MIN_GAMES_FOR_AVERAGE:
            continue
        avg = total / count
        (starters if avg >= STARTER_MINUTES else bench).append((margin, l.minutes / avg))

    s_fit, b_fit = _fit(starters), _fit(bench)
    starter_slope, starter_t = (_clamp(-s_fit[0], STARTER_SLOPE_BOUNDS), s_fit[1]) if s_fit \
        else (0.0, DEFAULT_THRESHOLD)
    bench_slope, bench_t = (_clamp(b_fit[0], BENCH_SLOPE_BOUNDS), b_fit[1]) if b_fit \
        else (0.0, DEFAULT_THRESHOLD)
    return BlowoutModel(starter_slope, starter_t, bench_slope, bench_t)


def factor(model: BlowoutModel, expected_margin: float, is_starter: bool) -> float:
    """Multiplicateur des minutes (donc de la projection) d'un joueur, selon
    l'écart attendu (signe indifférent : victoire ou défaite large)."""
    if is_starter:
        excess = max(0.0, abs(expected_margin) - model.starter_threshold)
        value = 1.0 - model.starter_slope * excess
    else:
        excess = max(0.0, abs(expected_margin) - model.bench_threshold)
        value = 1.0 + model.bench_slope * excess
    return _clamp(value, FACTOR_BOUNDS)
