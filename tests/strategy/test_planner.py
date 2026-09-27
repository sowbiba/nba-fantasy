from datetime import date, timedelta

from engine.stats.projection import GameContext
from engine.strategy.planner import TOP_PER_NIGHT, Cell, PlanEntry, solve

D0 = date(2026, 11, 1)
CTX = GameContext("XXX", True, 1, 1.0)


def _cell(pid, day, value):
    return Cell(pid, D0 + timedelta(days=day), value, 1.0, value, CTX)


def test_match_facile_a_j20_fait_jouer_un_autre_joueur_ce_soir():
    # X : 40 ce soir, 60 à J+20. Y : 38 ce soir. Jouer X ce soir le bloque pour J+20.
    cells = [_cell(1, 0, 40.0), _cell(1, 20, 60.0), _cell(2, 0, 38.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=20)])
    assert plan[D0].cell.player_id == 2
    assert plan[D0 + timedelta(days=20)].cell.player_id == 1


def test_un_joueur_au_plus_une_fois():
    cells = [_cell(1, 0, 50.0), _cell(1, 1, 50.0), _cell(2, 1, 10.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=1)])
    assert {e.cell.player_id for e in plan.values()} == {1, 2}


def test_soiree_sans_candidat_absente_du_plan():
    plan = solve([_cell(1, 0, 50.0)], [D0, D0 + timedelta(days=1)])
    assert list(plan) == [D0]


def test_elagage_garde_les_meilleurs_par_soiree():
    cells = [_cell(pid, 0, float(pid)) for pid in range(TOP_PER_NIGHT + 10)]
    plan = solve(cells, [D0])
    assert plan[D0].cell.player_id == TOP_PER_NIGHT + 9


def test_plan_vide():
    assert solve([], []) == {}


def test_maximise_la_valeur_totale_quitte_a_laisser_une_soiree_vide():
    # A : 100 ce soir, 1 à J+5. B : 1 ce soir. Maximiser la valeur totale.
    cells = [_cell(1, 0, 100.0), _cell(1, 5, 1.0), _cell(2, 0, 1.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=5)])
    assert plan == {D0: PlanEntry(_cell(1, 0, 100.0), False)}


def test_soiree_obligatoire_prise_meme_negative():
    # A : -5 ce soir. B : -2 ce soir. Soirée obligatoire → pick le moins mauvais.
    cells = [_cell(1, 0, -5.0), _cell(2, 0, -2.0)]
    plan = solve(cells, [D0], required={D0})
    assert plan[D0].cell.player_id == 2


def test_soiree_future_negative_laissee_vide():
    # A : -5 à J+1. Pas d'obligation → aucun pick.
    cells = [_cell(1, 1, -5.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=1)])
    assert plan == {}


# --- MILP + x2 mensuel (S3) -------------------------------------------------

import random

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment

import engine.strategy.planner as planner_mod

D1 = date(2026, 11, 3)
D2 = date(2026, 11, 10)
D3 = date(2026, 11, 17)
D4 = date(2026, 12, 2)


def _xcell(pid, night, value, x2=0.0):
    return Cell(pid, night, value, 1.0, value, CTX, x2_gain=x2)


def test_milp_egal_affectation_sans_x2():
    # 3 joueurs, 3 soirées, valeurs choisies pour que le glouton se trompe
    cells = [_xcell(1, D1, 10), _xcell(1, D2, 9), _xcell(2, D1, 9), _xcell(2, D2, 1), _xcell(3, D3, 5)]
    plan = solve(cells, [D1, D2, D3])
    assert sum(e.cell.value for e in plan.values()) == 23          # optimum : 2→D1, 1→D2, 3→D3
    assert not any(e.is_x2 for e in plan.values())


def _lsa_optimum(cells, nights):
    """Ancien solveur (linear_sum_assignment + colonnes fictives) : oracle."""
    players = sorted({c.player_id for c in cells})
    row = {p: i for i, p in enumerate(players)}
    col = {d: j for j, d in enumerate(nights)}
    cost = np.full((len(players), len(nights) + len(players)), 1e9)
    for i in range(len(players)):
        cost[i, len(nights) + i] = 0
    for c in cells:
        cost[row[c.player_id], col[c.night]] = min(cost[row[c.player_id], col[c.night]], -c.value)
    r, k = linear_sum_assignment(cost)
    return -sum(cost[a, b] for a, b in zip(r, k) if b < len(nights) and cost[a, b] < 1e9)


def test_milp_egal_oracle_affectation_sur_instances_aleatoires():
    rng = random.Random(42)
    for _ in range(25):
        nights = [date(2026, 10, 1) + timedelta(days=k) for k in range(rng.randint(1, 12))]
        cells = [Cell(pid, d, 0.0, 1.0, round(rng.uniform(-10, 60), 2), CTX)
                 for pid in range(rng.randint(1, 15)) for d in nights if rng.random() < 0.4]
        if not cells:
            continue
        plan = solve(cells, nights)
        assert sum(e.cell.value for e in plan.values()) == pytest.approx(_lsa_optimum(cells, nights), abs=1e-6)
        assert len({e.cell.player_id for e in plan.values()}) == len(plan)


def test_x2_sur_le_meilleur_gain_du_mois():
    cells = [_xcell(1, D1, 30, x2=20), _xcell(2, D2, 30, x2=35)]   # même valeur, gain x2 différent
    plan = solve(cells, [D1, D2], x2_months={(D1.year, D1.month): False})
    assert [d for d, e in plan.items() if e.is_x2] == [D2]


def test_x2_non_force_si_gain_negatif():
    cells = [_xcell(1, D1, 10, x2=-5)]
    assert not solve(cells, [D1], x2_months={(D1.year, D1.month): False})[D1].is_x2


def test_x2_force_en_fin_de_mois():
    cells = [_xcell(1, D1, 10, x2=-5)]
    assert solve(cells, [D1], x2_months={(D1.year, D1.month): True})[D1].is_x2


def test_pas_de_x2_hors_mois_listes():
    cells = [_xcell(1, D1, 10, x2=50)]
    assert not solve(cells, [D1], x2_months={})[D1].is_x2


def test_un_seul_x2_par_mois_et_un_par_mois_distinct():
    cells = [_xcell(1, D1, 30, x2=20), _xcell(2, D2, 30, x2=25), _xcell(3, D4, 30, x2=10)]
    months = {(D1.year, D1.month): False, (D4.year, D4.month): False}
    plan = solve(cells, [D1, D2, D4], x2_months=months)
    assert [d for d, e in plan.items() if e.is_x2] == [D2, D4]


def test_x2_peut_changer_l_affectation():
    # Sans x2 : A (1) à D1 (40) et B (2) à D2 (35) = 75. A à D2 vaut 38 mais
    # son gain x2 y est énorme : l'optimum garde A pour la soirée doublée.
    cells = [_xcell(1, D1, 40, x2=10), _xcell(1, D2, 38, x2=38), _xcell(2, D1, 36, x2=5), _xcell(2, D2, 35, x2=5)]
    plan = solve(cells, [D1, D2], x2_months={(2026, 11): False})
    assert plan[D2].cell.player_id == 1 and plan[D2].is_x2
    assert plan[D1].cell.player_id == 2


def test_x2_limite_aux_soirees_eligibles():
    # Avril : soirée SR (D_sr) et soirée PO (D_po). R10 : x2 en SR seulement.
    d_sr, d_po = date(2027, 4, 10), date(2027, 4, 20)
    cells = [_xcell(1, d_sr, 10, x2=1), _xcell(2, d_po, 50, x2=50)]
    plan = solve(cells, [d_sr, d_po], x2_months={(2027, 4): True}, x2_nights={d_sr})
    assert plan[d_sr].is_x2 and not plan[d_po].is_x2


def test_x2_force_infaisable_relance_sans_forcer(caplog):
    # Ce soir (31/10, obligatoire) : seul A. Novembre (forcé) : seul A aussi.
    # A ne peut pas jouer deux fois → forcer le x2 de novembre est infaisable :
    # relance sans forcer, A joue ce soir, aucun x2.
    today, nov = date(2026, 10, 31), date(2026, 11, 5)
    cells = [_xcell(1, today, 20), _xcell(1, nov, 25, x2=-3)]
    with caplog.at_level("WARNING", logger=planner_mod.__name__):
        plan = solve(cells, [today, nov], required={today}, x2_months={(2026, 11): True})
    assert plan == {today: PlanEntry(_xcell(1, today, 20), False)}
    assert "relance sans forcer" in caplog.text


def test_temps_de_resolution_realiste():
    import time
    rng = random.Random(7)
    nights = [date(2026, 11, 15) + timedelta(days=k) for k in range(30)]
    cells = [Cell(rng.randrange(250), d, 0.0, 0.9, rng.uniform(10, 60), CTX, x2_gain=rng.uniform(-5, 55))
             for d in nights for _ in range(40)]
    t0 = time.perf_counter()
    plan = solve(cells, nights, required={nights[0]}, x2_months={(2026, 11): True, (2026, 12): False})
    elapsed = time.perf_counter() - t0
    assert sum(e.is_x2 for e in plan.values()) in (1, 2)
    assert elapsed < 5.0


# --- I-1 : limite de temps, solution réalisable acceptée ----------------------

class _FakeRes:
    def __init__(self, status, x, message="fake"):
        self.status, self.x, self.message = status, x, message


def test_milp_a_une_limite_de_temps(monkeypatch):
    seen = {}
    real = planner_mod.milp

    def spy(*args, **kwargs):
        seen.update(kwargs.get("options") or {})
        return real(*args, **kwargs)

    monkeypatch.setattr(planner_mod, "milp", spy)
    solve([_cell(1, 0, 10.0)], [D0])
    assert seen["time_limit"] == planner_mod.MILP_TIME_LIMIT_S


def test_statut_1_avec_solution_realisable_accepte(monkeypatch):
    # Limite de temps atteinte (statut 1) mais une solution réalisable existe :
    # on la garde plutôt que d'échouer.
    monkeypatch.setattr(planner_mod, "milp", lambda *a, **k: _FakeRes(1, np.array([0.0, 1.0])))
    plan = solve([_cell(1, 0, 10.0), _cell(2, 0, 5.0)], [D0])
    assert plan[D0].cell.player_id == 2


def test_statut_1_sans_solution_leve(monkeypatch):
    monkeypatch.setattr(planner_mod, "milp", lambda *a, **k: _FakeRes(1, None))
    with pytest.raises(RuntimeError):
        solve([_cell(1, 0, 10.0)], [D0])
