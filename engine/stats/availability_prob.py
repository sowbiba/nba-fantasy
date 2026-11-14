"""P(joue) : statut ESPN, date de retour, motif DNP récent, repos de back-to-back.

La fuite n°1 de 2025-26 (audit §9) : 17 zéros sur 162 picks. Un zéro coûte
la soirée ET bloque le joueur (R7), d'où une P(joue) aussi honnête que possible.
"""
from datetime import date, timedelta

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

# Blessés signalés (correctif 2026-11, cas Edwards : Out jusqu'au 21/12 mais
# planifié à 100 % car seul le taux de présence comptait — les matchs manqués
# ne laissent pas de log). Choix utilisateur « aucun risque » : tout joueur
# au statut signalé est écarté des soirées futures jusqu'à INJURY_SAFETY_DAYS
# jours après sa date de retour ESPN ; sans date, sur les INJURY_SAFETY_DAYS
# premiers jours.
INJURY_SAFETY_DAYS = 7

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


def parse_return_date(value) -> date | None:
    """Date de retour ESPN (`players.injury_return_date`, texte ISO) ou None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def quarantined(*, injury_status: str | None, night: date | None, return_date: date | None,
                days_ahead: int | None) -> bool:
    """Règle « aucun risque » : le joueur est écarté de `night`.

    - forfait pour la saison ;
    - date de retour connue : jusqu'à INJURY_SAFETY_DAYS jours après elle,
      que le statut soit encore affiché ou non (ESPN retire le joueur de sa
      liste le jour de son retour : `daily_sync` garde alors la date) ;
    - statut signalé sans date : sur les INJURY_SAFETY_DAYS premiers jours.
    """
    if injury_status == "Out For Season":
        return True
    if return_date is not None and night is not None:
        return night < return_date + timedelta(days=INJURY_SAFETY_DAYS)
    return bool(injury_status) and days_ahead is not None and days_ahead <= INJURY_SAFETY_DAYS


def tonight_p_play(*, injury_status: str | None, recent_logs: list[dict], is_b2b_second: bool,
                   exp_minutes: float, night: date | None = None, return_date: date | None = None) -> float:
    """Le soir même : tout statut signalé (même « Probable », même inconnu)
    écarte le joueur, comme la quarantaine de retour ; sinon motif DNP
    récent et repos de back-to-back."""
    if injury_status or quarantined(injury_status=None, night=night, return_date=return_date, days_ahead=0):
        return 0.0
    return dnp_risk_factor(recent_logs) * _b2b(is_b2b_second, exp_minutes)


def future_p_play(*, injury_status: str | None, availability_rate: float,
                  is_b2b_second: bool, exp_minutes: float, night: date | None = None,
                  return_date: date | None = None, days_ahead: int | None = None) -> float:
    """Soirées futures : joueur écarté (0) par la règle « aucun risque »
    (`quarantined`). Sinon, taux de présence récent."""
    if quarantined(injury_status=injury_status, night=night, return_date=return_date, days_ahead=days_ahead):
        return 0.0
    return availability_rate * _b2b(is_b2b_second, exp_minutes)
