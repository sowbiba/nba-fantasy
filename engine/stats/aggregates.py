"""Colonnes players.avg_* lues par le front actuel (listes, fiches joueur),
calculées sur la saison en cours (DNP exclus)."""
from statistics import mean, pstdev

from engine.stats.profile import GameLog

MIN_SPLIT_GAMES = 4
EMPTY = {"avg_ttfl_l5": 0, "avg_ttfl_l10": 0, "avg_ttfl_l20": 0, "avg_ttfl_season": 0,
         "stddev_ttfl": 0, "home_avg": 0, "away_avg": 0, "avg_minutes_l10": 0}


def player_aggregates(logs: list[GameLog]) -> dict:
    played = sorted((l for l in logs if l.minutes > 0), key=lambda l: l.date, reverse=True)
    if not played:
        return dict(EMPTY)
    scores = [l.ttfl for l in played]
    season = mean(scores)
    home = [l.ttfl for l in played if l.is_home]
    away = [l.ttfl for l in played if not l.is_home]
    return {
        "avg_ttfl_l5": mean(scores[:5]),
        "avg_ttfl_l10": mean(scores[:10]),
        "avg_ttfl_l20": mean(scores[:20]),
        "avg_ttfl_season": season,
        "stddev_ttfl": pstdev(scores) if len(scores) >= 3 else 0,
        "home_avg": mean(home) if len(home) >= MIN_SPLIT_GAMES else season,
        "away_avg": mean(away) if len(away) >= MIN_SPLIT_GAMES else season,
        "avg_minutes_l10": mean(l.minutes for l in played[:10]),
    }
