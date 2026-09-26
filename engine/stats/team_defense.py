"""Facteur défensif par poste : TTFL par minute concédé par l'équipe au
poste, rapporté à la moyenne de la ligue. L'adversaire se lit dans
game_logs.team (équipe au moment du match), ce qui corrige l'attribution
erronée après transferts (audit §2).

Saison en cours fondue avec la saison précédente régressée de moitié vers
1.0 (effectifs changés, S6). Borné à [0.85, 1.15].
"""
from collections import defaultdict

from engine.stats.profile import GameLog

POSITIONS = ("G", "F", "C")
PRIOR_GAMES = 15
PRIOR_REGRESSION = 0.5
FACTOR_BOUNDS = (0.85, 1.15)


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


def _league(totals) -> dict[str, float]:
    league = {}
    for pos in POSITIONS:
        ttfl = sum(t[pos][0] for t in totals.values())
        minutes = sum(t[pos][1] for t in totals.values())
        league[pos] = ttfl / minutes if minutes > 0 else 0.0
    return league


def defense_factors(current_logs: list[GameLog], prior_logs: list[GameLog],
                    games: dict[str, dict], positions: dict[int, str]) -> dict[str, dict[str, float]]:
    cur, cur_games = _allowed(current_logs, games, positions)
    pri, _ = _allowed(prior_logs, games, positions)
    league_cur, league_pri = _league(cur), _league(pri)
    factors: dict[str, dict[str, float]] = {}
    for team in set(cur) | set(pri):
        n = len(cur_games.get(team, ()))
        weight = n / (n + PRIOR_GAMES)
        factors[team] = {}
        for pos in POSITIONS:
            ttfl, minutes = cur[team][pos] if team in cur else (0.0, 0.0)
            f_cur = (ttfl / minutes) / league_cur[pos] if minutes > 0 and league_cur[pos] > 0 else 1.0
            ttfl_p, minutes_p = pri[team][pos] if team in pri else (0.0, 0.0)
            if minutes_p > 0 and league_pri[pos] > 0:
                f_pri = 1.0 + PRIOR_REGRESSION * ((ttfl_p / minutes_p) / league_pri[pos] - 1.0)
            else:
                f_pri = 1.0
            factors[team][pos] = _clamp(weight * f_cur + (1 - weight) * f_pri)
    return factors


def opp_factor(factors: dict[str, dict[str, float]], opponent: str, position: str) -> float:
    return factors.get(opponent, {}).get(position, 1.0)
