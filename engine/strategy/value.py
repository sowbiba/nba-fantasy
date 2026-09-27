"""Espérance complète d'un pick (S1) et décote du futur (S2).

Picker un joueur le bloque 30 jours (R3), qu'il joue ou non (R7). S'il ne
joue pas, ce blocage est perdu pour rien : on retire donc
(1 − P(joue)) × lock_value, où lock_value est la meilleure espérance future
du joueur dans la fenêtre de cooldown, décotée par l'incertitude.
"""
from engine.rules.availability import COOLDOWN_DAYS

FUTURE_DECAY = 0.985  # par jour d'avance ; à calibrer par backtest (L2)


def discount(days_ahead: int) -> float:
    return FUTURE_DECAY ** days_ahead


def lock_value(future: list[tuple[int, float]]) -> float:
    values = [discount(k) * ev for k, ev in future if 1 <= k < COOLDOWN_DAYS]
    return max(values, default=0.0)


def tonight_value(p_play: float, projection: float, lock: float) -> float:
    return p_play * projection - (1.0 - p_play) * lock


def future_value(days_ahead: int, p_play: float, projection: float) -> float:
    return discount(days_ahead) * p_play * projection


# S3 / R10 : un x2 par mois de novembre à avril (mois de la date US).
X2_MONTHS = frozenset({11, 12, 1, 2, 3, 4})
X2_RISK_K = 0.5   # pénalité de risque (× écart-type) ; à calibrer par backtest (L2)


def x2_gain(p_play: float, projection: float, stddev: float) -> float:
    """Gain attendu du x2 posé sur ce pick : le score est doublé (même
    négatif), pénalisé par le risque ; un DNP perd le x2 (gain nul)."""
    return p_play * (projection - X2_RISK_K * stddev)
