from datetime import date

from engine.rules.scoring import compute_ttfl_score, night_points, period_average


def test_formule_exemple_officiel():
    # Exemple de la FAQ : 28 pts, 10 reb, 6 ast, 2 stl, 1 blk, 11/20, 3/7 à 3pts, 3/4 LF, 4 BP → 46
    assert compute_ttfl_score(
        pts=28, reb=10, ast=6, stl=2, blk=1, fgm=11, fga=20,
        tpm=3, tpa=7, ftm=3, fta=4, tov=4,
    ) == 46


def test_x2_double_le_score():
    assert night_points(53, is_x2=True) == 106


def test_x2_double_aussi_un_score_negatif():
    assert night_points(-7, is_x2=True) == -14


def test_x2_sur_un_zero_reste_zero():
    assert night_points(0, is_x2=True) == 0


def test_pick_pas_encore_score():
    assert night_points(None, is_x2=False) is None


def test_moyenne_compte_les_soirees_sans_pick_pour_zero():
    nights = [date(2025, 11, 1), date(2025, 11, 2), date(2025, 11, 3)]
    results = {date(2025, 11, 1): (40, False), date(2025, 11, 2): (20, True)}
    # (40 + 40 + 0) / 3 soirées éligibles, la 3e sans pick compte 0 (R14)
    assert period_average(nights, results) == 80 / 3


def test_moyenne_ignore_les_picks_pas_encore_scores():
    nights = [date(2025, 11, 1), date(2025, 11, 2)]
    results = {date(2025, 11, 1): (30, False), date(2025, 11, 2): (None, False)}
    assert period_average(nights, results) == 30.0


def test_moyenne_sans_soiree():
    assert period_average([], {}) is None
