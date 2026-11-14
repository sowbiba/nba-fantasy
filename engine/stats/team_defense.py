"""Facteur défensif d'ÉQUIPE : TTFL par minute concédé par l'équipe, tous
postes confondus, rapporté à la moyenne de la ligue. L'adversaire se lit
dans game_logs.team (équipe au moment du match), ce qui corrige
l'attribution erronée après transferts (audit §2).

Jusqu'au 14/11/2026 le facteur était calculé par poste (G/F/C) : trois fois
moins de données par case, et aucun pouvoir prédictif mesuré (corrélation
0,05 avec l'écart à la projection). Au niveau de l'équipe l'effet est net
sur 5 saisons : +2,0 points contre les 5 défenses les plus généreuses,
−1,9 contre les 5 plus avares (stars +3,0 / −2,4) —
data/box-scores/analyse_facteurs.py. Le dictionnaire renvoyé garde une
entrée par poste (même valeur) pour les appelants existants.

Saison en cours fondue avec la saison précédente régressée de moitié vers
1.0 (effectifs changés, S6), au poids des minutes observées. Borné à
[0.90, 1.10].
"""
from collections import defaultdict

from engine.stats.profile import GameLog

POSITIONS = ("G", "F", "C")
PRIOR_MINUTES = 3600.0   # ≈ 15 matchs d'équipe (240 min par match)
PRIOR_REGRESSION = 0.5
FACTOR_BOUNDS = (0.90, 1.10)


def _clamp(value: float) -> float:
    return max(FACTOR_BOUNDS[0], min(FACTOR_BOUNDS[1], value))


def _allowed(logs: list[GameLog], games: dict[str, dict], positions: dict[int, str]):
    totals: dict[str, dict[str, list[float]]] = defaultdict(lambda: {p: [0.0, 0.0] for p in POSITIONS})
    game_count: dict[str, set[str]] = defaultdict(set)
    for log in logs:
        game = games.get(log.game_id)
        if not game or log.minutes <= 0:
            continue
        if log.team == game["home_team"]:
            opponent = game["away_team"]
        elif log.team == game["away_team"]:
            opponent = game["home_team"]
        else:
            continue
        pos = positions.get(log.player_id, "F")
        pos = pos if pos in POSITIONS else "F"
        totals[opponent][pos][0] += log.ttfl
        totals[opponent][pos][1] += log.minutes
        game_count[opponent].add(log.game_id)
    return totals, game_count


def _team(totals: dict[str, list[float]]) -> tuple[float, float]:
    return sum(t[0] for t in totals.values()), sum(t[1] for t in totals.values())


def defense_factors(current_logs: list[GameLog], prior_logs: list[GameLog],
                    games: dict[str, dict], positions: dict[int, str]) -> dict[str, dict[str, float]]:
    cur, _ = _allowed(current_logs, games, positions)
    pri, _ = _allowed(prior_logs, games, positions)

    def league(table) -> float:
        ttfl = sum(_team(t)[0] for t in table.values())
        minutes = sum(_team(t)[1] for t in table.values())
        return ttfl / minutes if minutes > 0 else 0.0

    league_cur, league_pri = league(cur), league(pri)
    factors: dict[str, dict[str, float]] = {}
    for team in set(cur) | set(pri):
        ttfl, minutes = _team(cur[team]) if team in cur else (0.0, 0.0)
        weight = minutes / (minutes + PRIOR_MINUTES)
        f_cur = (ttfl / minutes) / league_cur if minutes > 0 and league_cur > 0 else 1.0
        ttfl_p, minutes_p = _team(pri[team]) if team in pri else (0.0, 0.0)
        if minutes_p > 0 and league_pri > 0:
            f_pri = 1.0 + PRIOR_REGRESSION * ((ttfl_p / minutes_p) / league_pri - 1.0)
        else:
            f_pri = 1.0
        value = _clamp(weight * f_cur + (1 - weight) * f_pri)
        factors[team] = {pos: value for pos in POSITIONS}
    return factors


def opp_factor(factors: dict[str, dict[str, float]], opponent: str, position: str) -> float:
    return factors.get(opponent, {}).get(position, 1.0)
