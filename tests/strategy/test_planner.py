from datetime import date, timedelta

from engine.stats.projection import GameContext
from engine.strategy.planner import TOP_PER_NIGHT, Cell, solve

D0 = date(2026, 11, 1)
CTX = GameContext("XXX", True, 1, 1.0)


def _cell(pid, day, value):
    return Cell(pid, D0 + timedelta(days=day), value, 1.0, value, CTX)


def test_match_facile_a_j20_fait_jouer_un_autre_joueur_ce_soir():
    # X : 40 ce soir, 60 à J+20. Y : 38 ce soir. Jouer X ce soir le bloque pour J+20.
    cells = [_cell(1, 0, 40.0), _cell(1, 20, 60.0), _cell(2, 0, 38.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=20)])
    assert plan[D0].player_id == 2
    assert plan[D0 + timedelta(days=20)].player_id == 1


def test_un_joueur_au_plus_une_fois():
    cells = [_cell(1, 0, 50.0), _cell(1, 1, 50.0), _cell(2, 1, 10.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=1)])
    assert {c.player_id for c in plan.values()} == {1, 2}


def test_soiree_sans_candidat_absente_du_plan():
    plan = solve([_cell(1, 0, 50.0)], [D0, D0 + timedelta(days=1)])
    assert list(plan) == [D0]


def test_elagage_garde_les_meilleurs_par_soiree():
    cells = [_cell(pid, 0, float(pid)) for pid in range(TOP_PER_NIGHT + 10)]
    plan = solve(cells, [D0])
    assert plan[D0].player_id == TOP_PER_NIGHT + 9


def test_plan_vide():
    assert solve([], []) == {}


def test_maximise_la_valeur_totale_quitte_a_laisser_une_soiree_vide():
    # A : 100 ce soir, 1 à J+5. B : 1 ce soir. Maximiser la valeur totale.
    cells = [_cell(1, 0, 100.0), _cell(1, 5, 1.0), _cell(2, 0, 1.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=5)])
    assert plan == {D0: _cell(1, 0, 100.0)}


def test_soiree_obligatoire_prise_meme_negative():
    # A : -5 ce soir. B : -2 ce soir. Soirée obligatoire → pick le moins mauvais.
    cells = [_cell(1, 0, -5.0), _cell(2, 0, -2.0)]
    plan = solve(cells, [D0], required={D0})
    assert plan[D0].player_id == 2


def test_soiree_future_negative_laissee_vide():
    # A : -5 à J+1. Pas d'obligation → aucun pick.
    cells = [_cell(1, 1, -5.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=1)])
    assert plan == {}
