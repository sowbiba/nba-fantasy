from datetime import date, timedelta

from engine.stats.aggregates import player_aggregates
from engine.stats.profile import GameLog


def _log(i, minutes, ttfl, home):
    return GameLog(1, f"g{i}", date(2026, 12, 1) - timedelta(days=i), "2026-27", "DEN", minutes, ttfl, home)


def test_aggregats_ignorent_les_dnp():
    logs = [_log(0, 0, 0, True)] + [_log(i, 30, 40, i % 2 == 0) for i in range(1, 11)]
    a = player_aggregates(logs)
    assert a["avg_ttfl_l5"] == 40.0 and a["avg_ttfl_season"] == 40.0
    assert a["avg_minutes_l10"] == 30.0


def test_split_domicile_exterieur_avec_garde_d_echantillon():
    logs = [_log(1, 30, 50, True), _log(2, 30, 30, False), _log(3, 30, 40, False)]
    a = player_aggregates(logs)
    assert a["home_avg"] == a["avg_ttfl_season"]        # < 4 matchs : repli sur la moyenne


def test_aggregats_vides():
    assert player_aggregates([])["avg_ttfl_season"] == 0
