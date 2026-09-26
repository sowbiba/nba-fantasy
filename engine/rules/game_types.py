"""R11 / R12 — type et saison d'un match NBA, déduits de son identifiant.

Identifiants NBA : 3 chiffres de type + 2 chiffres d'année de début de saison
(« 0022500001 » = saison régulière 2025-26). Les matchs `hist_<date>` sont
les supports des picks 2025-26 importés : saison régulière, saison déduite
de la date. Miroir SQL : game_type_of / season_of (migration 017).
"""
from datetime import date

_PREFIX_TYPES = {
    "001": "preseason",
    "002": "regular",
    "003": "allstar",
    "004": "playoffs",
    "005": "playin",
    "006": "cup_final",
}

ELIGIBLE_TYPES = frozenset({"regular", "cup_final", "playoffs"})


def game_type_of(game_id: str) -> str:
    if game_id.startswith("hist_"):
        return "regular"
    return _PREFIX_TYPES.get(game_id[:3], "unknown")


def _season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_of(game_id: str, game_date: date) -> str:
    if game_id[:3] in _PREFIX_TYPES and game_id[3:5].isdigit():
        return _season_label(2000 + int(game_id[3:5]))
    start = game_date.year if game_date.month >= 9 else game_date.year - 1
    return _season_label(start)


def is_eligible(game_type: str) -> bool:
    return game_type in ELIGIBLE_TYPES


def mode_of(game_type: str) -> str:
    return "playoffs" if game_type == "playoffs" else "regular"
