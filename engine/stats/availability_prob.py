"""P(joue) : statut ESPN, motif DNP récent, repos de back-to-back.

La fuite n°1 de 2025-26 (audit §9) : 17 zéros sur 162 picks. Un zéro coûte
la soirée ET bloque le joueur (R7), d'où une P(joue) aussi honnête que possible.
"""

# Probabilité de jouer selon le statut ESPN (observation empirique TTFL).
INJURY_PLAY_PROBABILITY = {
    "Out": 0.00,
    "Out For Season": 0.00,
    "Suspended": 0.00,
    "Doubtful": 0.20,
    "Questionable": 0.55,
    "Day-To-Day": 0.65,
    "Game-Time Decision": 0.55,
    "Probable": 0.85,
}

# Statuts qui retirent le joueur des candidats du soir.
HARD_OUT_STATUSES = frozenset({"Out", "Doubtful", "Out For Season", "Suspended"})

# 2e soir d'un back-to-back : les gros minutages sont parfois mis au repos
# (load management). À recalibrer par backtest (L2).
B2B_REST_FACTOR = 0.93
B2B_REST_MIN_MINUTES = 30.0


def play_probability(status: str | None) -> float:
    if not status:
        return 1.0
    return INJURY_PLAY_PROBABILITY.get(status, 1.0)


def dnp_risk_factor(recent_logs: list[dict]) -> float:
    """Pénalité pour un motif DNP que le flux ESPN n'a pas encore reflété.
    `recent_logs` du plus récent au plus ancien, avec la clé minutes."""
    if not recent_logs:
        return 1.0
    last3 = recent_logs[:3]
    dnp = sum(1 for log in last3 if (log.get("minutes") or 0) == 0)
    if len(last3) < 3:
        return 0.55 if dnp == len(last3) and dnp >= 1 else 1.0
    if dnp == 3:
        return 0.30
    if dnp == 2:
        return 0.55
    if dnp == 1:
        return 0.75 if (last3[0].get("minutes") or 0) == 0 else 0.90
    return 1.0


def _b2b(is_b2b_second: bool, exp_minutes: float) -> float:
    return B2B_REST_FACTOR if is_b2b_second and exp_minutes >= B2B_REST_MIN_MINUTES else 1.0


def p_play(*, injury_status: str | None, recent_logs: list[dict],
           is_b2b_second: bool, exp_minutes: float) -> float:
    return play_probability(injury_status) * dnp_risk_factor(recent_logs) * _b2b(is_b2b_second, exp_minutes)


def future_p_play(*, injury_status: str | None, availability_rate: float,
                  is_b2b_second: bool, exp_minutes: float) -> float:
    """Soirées futures : le statut du jour ne dit presque rien d'un match dans
    10 jours, sauf une saison terminée. On prend le taux de présence récent."""
    if injury_status == "Out For Season":
        return 0.0
    return availability_rate * _b2b(is_b2b_second, exp_minutes)
