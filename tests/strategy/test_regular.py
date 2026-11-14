from datetime import date, datetime, timedelta

import pytest

from engine.rules.availability import PickRow, SeriesRow
from engine.rules.calendar import PARIS, Night
from engine.stats.profile import PlayerProfile
from engine.strategy.regular import DecisionInputs, decide

TODAY = date(2026, 11, 2)


def _night(d, n=1):
    return Night(d, "2026-27", "regular", n, datetime(d.year, d.month, d.day, 23, tzinfo=PARIS), False)


def _game(gid, d, home, away, gtype="regular"):
    return {"id": gid, "date": d.isoformat(), "home_team": home, "away_team": away, "game_type": gtype}


def _prof(pid, eff=1.5, minutes=34.0):
    return PlayerProfile(pid, eff, minutes, 10, 8.0, 0.95)


PLAYERS = {
    1: {"id": 1, "name": "Star DEN", "team": "DEN", "position": "C", "injury_status": None, "active": True},
    2: {"id": 2, "name": "Guard LAL", "team": "LAL", "position": "G", "injury_status": None, "active": True},
    3: {"id": 3, "name": "Bench DEN", "team": "DEN", "position": "F", "injury_status": None, "active": True},
}


def _inputs(**over):
    base = dict(
        today=TODAY,
        nights=[_night(TODAY), _night(TODAY + timedelta(days=20))],
        games=[_game("g1", TODAY, "DEN", "LAL"), _game("g2", TODAY + timedelta(days=20), "DEN", "WAS")],
        players=PLAYERS,
        profiles={1: _prof(1), 2: _prof(2, eff=1.2), 3: _prof(3, eff=1.0, minutes=10.0)},
        recent_logs={1: [{"minutes": 34}] * 3, 2: [{"minutes": 33}] * 3, 3: [{"minutes": 10}] * 3},
        defense={"WAS": {"C": 1.15}},
        picks=[], second_chances=[], series=[],
    )
    base.update(over)
    return DecisionInputs(**base)


def test_decide_reco_du_soir_triee_par_valeur_et_filtre_minutes():
    d = decide(_inputs())
    assert d.tonight == TODAY
    ids = [r.cell.player_id for r in d.recommendations]
    assert 3 not in ids                       # 10 min attendues < 15
    assert ids == sorted(ids, key=lambda pid: -next(r.cell.value for r in d.recommendations if r.cell.player_id == pid))


def test_decide_decay_parametrable_change_le_lock_value():
    d_default = decide(_inputs())
    d_decay = decide(_inputs(), decay=0.5)
    star_default = next(r for r in d_default.recommendations if r.cell.player_id == 1)
    star_decay = next(r for r in d_decay.recommendations if r.cell.player_id == 1)
    # Seule soirée future du fixture : J+20 -> lock_value = decay**20 * ev.
    assert 0 < star_decay.lock_value < star_default.lock_value
    assert star_decay.lock_value == pytest.approx(star_default.lock_value * (0.5 / 0.985) ** 20)


def test_decide_lock_value_et_meilleur_futur():
    d = decide(_inputs())
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.best_future is not None and star.best_future.night == TODAY + timedelta(days=20)
    assert star.lock_value > 0
    assert star.locked_until == TODAY + timedelta(days=30)


def test_decide_plan_joue_la_star_a_son_meilleur_soir():
    d = decide(_inputs())
    assert d.plan[TODAY + timedelta(days=20)].cell.player_id == 1
    assert d.plan[TODAY].cell.player_id == 2


def test_decide_tonight_source_best_available_par_defaut():
    # Le meilleur choix S1 du soir (joueur 1) diffère de plan[today] (joueur 2).
    d = decide(_inputs())
    assert d.plan[TODAY].cell.player_id == 2
    assert d.recommendations[0].cell.player_id == 1


def test_decide_tonight_source_plan_place_le_joueur_du_plan_en_tete():
    d = decide(_inputs(), tonight_source="plan")
    ids = [r.cell.player_id for r in d.recommendations]
    assert ids == [2, 1]  # joueur du plan en tête, le reste garde l'ordre par valeur
    assert ids.count(2) == 1  # ne doit apparaître qu'une seule fois


def test_decide_exclut_cooldown_et_out():
    players = {**PLAYERS, 2: {**PLAYERS[2], "injury_status": "Out"}}
    picks = [PickRow(9, 1, TODAY - timedelta(days=10), "regular", "2026-27")]
    d = decide(_inputs(players=players, picks=picks))
    assert [r.cell.player_id for r in d.recommendations] == []


# --- Réservations challengeables (2026-11) -----------------------------------
# Une réservation future ne bloque plus le moteur : le joueur réservé reste
# candidat ce soir, et la soirée réservée reste au plan, où un autre joueur
# peut la contester. Seule une réservation x2 reste figée.

LATER = TODAY + timedelta(days=20)
RIVAL = {4: {"id": 4, "name": "Wing WAS", "team": "WAS", "position": "F", "injury_status": None, "active": True}}


def _resa(pid=1, is_x2=False):
    return PickRow(7, pid, LATER, "regular", "2026-27", is_x2)


def _with_rival(eff, **over):
    """Un 4e joueur (WAS) joue aussi la soirée réservée à J+20."""
    base = _inputs()
    args = dict(players={**PLAYERS, **RIVAL}, profiles={**base.profiles, 4: _prof(4, eff=eff)},
                recent_logs={**base.recent_logs, 4: [{"minutes": 34}] * 3})
    args.update(over)
    return _inputs(**args)


def test_reservation_future_ne_change_pas_le_classement_du_soir():
    free = decide(_inputs())
    reserved = decide(_inputs(picks=[_resa()]))
    assert ([(r.cell.player_id, r.cell.value) for r in reserved.recommendations]
            == [(r.cell.player_id, r.cell.value) for r in free.recommendations])


def test_reservation_future_signalee_sur_la_reco_du_soir():
    d = decide(_inputs(picks=[_resa()]))
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.reserved_on == LATER
    assert all(r.reserved_on is None for r in d.recommendations if r.cell.player_id != 1)


def test_reservation_gardee_au_plan_si_aucun_ecart_net():
    # Ce soir est déjà pické (joueur 2) ; à J+20 le rival fait à peine mieux
    # que le joueur réservé (60,0 contre 59,8) : en dessous de la marge, le
    # plan garde la réservation.
    d = decide(_with_rival(eff=1.8, picks=[_resa(), PickRow(99, 2, TODAY, "regular", "2026-27")]))
    assert d.plan[LATER].cell.player_id == 1
    assert d.reservations[LATER].player_id == 1 and d.reservations[LATER].cell is not None


def test_reservation_contestee_si_un_autre_joueur_fait_nettement_mieux():
    d = decide(_with_rival(eff=2.2, picks=[_resa()]))
    assert d.plan[LATER].cell.player_id == 4
    assert d.plan[LATER].cell.value == pytest.approx(decide(_with_rival(eff=2.2)).plan[LATER].cell.value)


def test_reservation_contestee_si_le_joueur_reserve_est_out():
    players = {**PLAYERS, **RIVAL, 1: {**PLAYERS[1], "injury_status": "Out",
                                       "injury_return_date": (TODAY + timedelta(days=30)).isoformat()}}
    d = decide(_with_rival(eff=1.0, picks=[_resa()], players=players))
    assert d.plan[LATER].cell.player_id == 4
    assert d.reservations[LATER].cell.p_play == 0


def test_reservation_x2_reste_figee():
    d = decide(_with_rival(eff=2.2, picks=[_resa(is_x2=True)], x2_used_months=frozenset({(2026, 11)})))
    assert LATER not in d.plan                                   # soirée figée
    assert 1 not in [r.cell.player_id for r in d.recommendations]   # bloqué ce soir
    assert LATER not in d.reservations


def test_decide_debut_de_saison_utilise_le_prior():
    # Profil issu du prior seul (0 match courant) : projection > 0 (bug B5).
    profiles = {1: PlayerProfile(1, 1.4, 32.0, 0, 0.0, 0.9), 2: _prof(2), 3: _prof(3)}
    d = decide(_inputs(profiles=profiles))
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.cell.projection > 40


def test_decide_pas_de_reco_un_soir_sans_match():
    d = decide(_inputs(nights=[_night(TODAY + timedelta(days=20))]))
    assert d.tonight is None and d.recommendations == []


def test_decide_ignore_matchs_ineligibles():
    games = [_game("p1", TODAY, "DEN", "LAL", "preseason")]
    d = decide(_inputs(games=games, nights=[_night(TODAY)]))
    assert d.recommendations == []


def test_decide_ignore_match_fantome_en_po():
    # PO : NYK-BOS (round 2, réel) et ATL-MIA (round 1 déjà terminé 4-1
    # pour ATL, donc match fantôme) programmés la même soirée.
    d = date(2027, 5, 10)
    night = Night(d, "2025-26", "playoffs", 1, datetime(d.year, d.month, d.day, 23, tzinfo=PARIS), False)
    games = [
        {**_game("real", d, "NYK", "BOS", "playoffs"), "status": "scheduled", "season": "2025-26"},
        {**_game("phantom", d, "ATL", "MIA", "playoffs"), "status": "scheduled", "season": "2025-26"},
    ]
    players = {
        10: {"id": 10, "name": "Atl Player", "team": "ATL", "position": "F", "injury_status": None, "active": True},
        11: {"id": 11, "name": "Mia Player", "team": "MIA", "position": "F", "injury_status": None, "active": True},
        12: {"id": 12, "name": "Nyk Player", "team": "NYK", "position": "F", "injury_status": None, "active": True},
        13: {"id": 13, "name": "Bos Player", "team": "BOS", "position": "F", "injury_status": None, "active": True},
    }
    profiles = {pid: _prof(pid) for pid in players}
    recent_logs = {pid: [{"minutes": 34}] * 3 for pid in players}
    series = [
        SeriesRow("2025-26", 1, "ATL", "MIA", 4, 1, "completed"),  # rend ATL-MIA fantôme
        SeriesRow("2025-26", 1, "NYK", "ORL", 4, 2, "completed"),  # qualifie NYK au 1er tour
        SeriesRow("2025-26", 1, "BOS", "CLE", 4, 1, "completed"),  # qualifie BOS au 1er tour
    ]
    d_inputs = DecisionInputs(
        today=d, nights=[night], games=games, players=players, profiles=profiles,
        recent_logs=recent_logs, defense={}, picks=[], second_chances=[], series=series,
    )
    dec = decide(d_inputs)
    ids = {r.cell.player_id for r in dec.recommendations}
    assert ids == {12, 13}


def test_plan_ne_compte_pas_deux_fois_le_blocage():
    """Le planificateur ne doit pas décompter le blocage de 30 j deux fois :
    une fois via l'affectation elle-même (un joueur au plus une fois sur
    l'horizon), une fois via tonight_value. Valeurs calculées à la main
    (profils/ctx ci-dessous, opp_factor = 1.0 partout, defense={}) :

    - A (pid 201, DEN, domicile ce soir vs LAL puis domicile J+20 vs WAS) :
      base = 2.0 * 30 = 60 ; projection ce soir = 60 * 1.02 = 61.2.
      p ce soir = 1.0 (injury_status None) * 0.55 (dnp_risk_factor, 2 DNP
      sur les 3 derniers logs) * 1.0 (pas de b2b) = 0.55.
      → valeur planificateur ce soir (fix) = p*projection = 33.66.
      Projection J+20 (même config domicile) = 61.2 ; p_future =
      availability_rate (0.9) * 1.0 (pas de b2b) = 0.9.
      → future_value(20, 0.9, 61.2) = 0.985**20 * 0.9 * 61.2 ≈ 40.7.
      → lock = 40.7 (via lock_value) ; tonight_value(A) = 33.66 - 0.45*40.7
        ≈ 15.3 (valeur "recommandation", avec blocage compté une fois).

    - B (pid 202, SAC, extérieur ce soir vs GSW, aucun match futur dans la
      fenêtre) : base = 1.0 * 30 = 30 ; projection = 30 * 0.98 = 29.4 ;
      p = 1.0 (aucun DNP récent). valeur ce soir = tonight_value = 29.4
      (lock nul, pas de futur) — identique en tant que cellule planificateur.

    - C (pid 203, BOS, domicile J+20 vs MIA uniquement) : base = 2.0 * 30
      = 60 ; projection = 60 * 1.02 = 61.2 ; p_future = 1.0 (availability
      1.0, pas de b2b). → future_value(20, 1.0, 61.2) ≈ 45.2.

    Total si le plan joue A ce soir et C à J+20 (avec le correctif) :
    33.66 + 45.24 ≈ 78.9, contre B ce soir + A à J+20 (sans le correctif,
    car tonight_value(A)=15.3 < B=29.4 fait perdre A la case du soir) :
    29.4 + 40.7 ≈ 70.1. Le correctif fait donc gagner A ce soir + C à J+20.
    """
    d20 = TODAY + timedelta(days=20)
    nights = [_night(TODAY), _night(d20)]
    games = [
        _game("g_a_tonight", TODAY, "DEN", "LAL"),
        _game("g_a_j20", d20, "DEN", "WAS"),
        _game("g_b_tonight", TODAY, "GSW", "SAC"),
        _game("g_c_j20", d20, "BOS", "MIA"),
    ]
    players = {
        201: {"id": 201, "name": "A", "team": "DEN", "position": "F", "injury_status": None, "active": True},
        202: {"id": 202, "name": "B", "team": "SAC", "position": "F", "injury_status": None, "active": True},
        203: {"id": 203, "name": "C", "team": "BOS", "position": "F", "injury_status": None, "active": True},
    }
    profiles = {
        201: PlayerProfile(201, 2.0, 30.0, 10, 5.0, 0.9),
        202: PlayerProfile(202, 1.0, 30.0, 10, 5.0, 1.0),
        203: PlayerProfile(203, 2.0, 30.0, 10, 5.0, 1.0),
    }
    recent_logs = {
        201: [{"minutes": 0}, {"minutes": 0}, {"minutes": 30}],  # 2 DNP -> dnp_risk_factor 0.55
        202: [{"minutes": 30}] * 3,
        203: [{"minutes": 30}] * 3,
    }
    d_inputs = DecisionInputs(
        today=TODAY, nights=nights, games=games, players=players, profiles=profiles,
        recent_logs=recent_logs, defense={}, picks=[], second_chances=[], series=[],
    )
    dec = decide(d_inputs)
    assert dec.plan[TODAY].cell.player_id == 201
    assert dec.plan[d20].cell.player_id == 203


# --- x2 mensuel (S3, R10) ---------------------------------------------------

from engine.strategy.regular import _x2_months


def test_x2_mois_entierement_visible_force_son_x2():
    # Les deux soirées de novembre (02 et 22) sont dans l'horizon : le x2 de
    # novembre est forcé et posé sur une soirée du plan.
    inputs = _inputs()
    assert _x2_months(inputs, {n.date: n for n in inputs.nights}) == {(2026, 11): True}
    d = decide(inputs)
    assert sum(e.is_x2 for e in d.plan.values()) == 1


def test_x2_mois_deja_servi_sans_x2():
    d = decide(_inputs(x2_used_months=frozenset({(2026, 11)})))
    assert d.plan and not any(e.is_x2 for e in d.plan.values())


def test_x2_pas_en_octobre():
    today = date(2026, 10, 25)
    d = decide(_inputs(today=today, nights=[_night(today), _night(today + timedelta(days=3))],
                       games=[_game("g1", today, "DEN", "LAL"), _game("g2", today + timedelta(days=3), "DEN", "WAS")]))
    assert d.plan and not any(e.is_x2 for e in d.plan.values())


def test_x2_mois_non_visible_en_entier_non_force():
    # 25/10 : novembre visible jusqu'au 23/11, mais une soirée le 28/11 est
    # hors horizon → x2 de novembre disponible, pas forcé.
    today = date(2026, 10, 25)
    nights = [_night(today), _night(date(2026, 11, 5)), _night(date(2026, 11, 28))]
    inputs = _inputs(today=today, nights=nights)
    horizon = {n.date: n for n in nights if (n.date - today).days < 30}
    assert _x2_months(inputs, horizon) == {(2026, 11): False}


def test_x2_jamais_sur_une_soiree_de_playoffs():
    # Avril : la soirée PO du 20 est exclue du x2 ; la dernière soirée SR
    # (10/04) est dans l'horizon → forcé sur la soirée SR.
    today = date(2027, 4, 10)
    po = today + timedelta(days=10)
    night_po = Night(po, "2026-27", "playoffs", 1, datetime(po.year, po.month, po.day, 23, tzinfo=PARIS), False)
    d = decide(_inputs(today=today, nights=[_night(today), night_po],
                       games=[_game("g1", today, "DEN", "LAL"), _game("g2", po, "DEN", "WAS", "playoffs")]))
    assert d.plan[today].is_x2
    assert po not in d.plan or not d.plan[po].is_x2


# --- I-1 : un échec du planificateur ne prive pas la soirée de ses recos -------

def test_echec_du_planificateur_garde_les_recommandations(monkeypatch, caplog):
    import engine.strategy.regular as regular_mod

    def boom(*args, **kwargs):
        raise RuntimeError("planificateur : pas de solution (test)")

    monkeypatch.setattr(regular_mod, "solve", boom)
    with caplog.at_level("ERROR", logger=regular_mod.__name__):
        d = decide(_inputs())
    assert d.plan == {}
    assert [r.cell.player_id for r in d.recommendations] == [1, 2]
    assert "planificateur en échec" in caplog.text


# --- I-2 : x2 sur le pick déjà posé ----------------------------------------------

LAST_NOV = date(2026, 11, 30)


def _fin_de_mois(**over):
    # Ce soir = dernière soirée SR de novembre ; soirée suivante en décembre.
    dec = LAST_NOV + timedelta(days=5)
    base = dict(today=LAST_NOV, nights=[_night(LAST_NOV), _night(dec)],
                games=[_game("g1", LAST_NOV, "DEN", "LAL"), _game("g2", dec, "DEN", "WAS")])
    base.update(over)
    return _inputs(**base)


def test_pick_du_soir_derniere_soiree_du_mois_porte_le_x2():
    # L'utilisateur a pické le joueur 2 ce soir (dernière soirée de novembre,
    # x2 non utilisé) : le mois forcé garde sa variable sur ce pick.
    pick = PickRow(11, 2, LAST_NOV, "regular", "2026-27")
    d = decide(_fin_de_mois(picks=[pick]))
    assert d.plan[LAST_NOV].cell.player_id == 2
    assert d.plan[LAST_NOV].is_x2


def test_pick_du_soir_cellule_calculee_comme_les_autres():
    # Même projection/p_play que la cellule du joueur 2 sans pick (le
    # cooldown de son propre pick est ignoré, rien d'autre).
    sans_pick = decide(_fin_de_mois())
    ref = next(r.cell for r in sans_pick.recommendations if r.cell.player_id == 2)
    d = decide(_fin_de_mois(picks=[PickRow(11, 2, LAST_NOV, "regular", "2026-27")]))
    cell = d.plan[LAST_NOV].cell
    assert (cell.projection, cell.p_play, cell.ctx) == (ref.projection, ref.p_play, ref.ctx)
    assert cell.x2_gain != 0.0


def test_soiree_pickee_dans_un_mois_x2_deja_servi_exclue():
    pick = PickRow(11, 2, LAST_NOV, "regular", "2026-27")
    d = decide(_fin_de_mois(picks=[pick], x2_used_months=frozenset({(2026, 11)})))
    assert LAST_NOV not in d.plan


def test_soiree_pickee_hors_mois_x2_exclue():
    # Octobre : pas de x2 → la soirée pickée reste hors du plan comme avant.
    today = date(2026, 10, 25)
    pick = PickRow(11, 2, today, "regular", "2026-27")
    d = decide(_inputs(today=today, picks=[pick],
                       nights=[_night(today), _night(today + timedelta(days=3))],
                       games=[_game("g1", today, "DEN", "LAL"), _game("g2", today + timedelta(days=3), "DEN", "WAS")]))
    assert today not in d.plan


# --- Facteur « écart de force » (L3a §2) -----------------------------------

from engine.stats.blowout import BlowoutModel  # noqa: E402
from engine.strategy.config import BLOWOUT_ENABLED  # noqa: E402

BLOWOUT = BlowoutModel(starter_slope=0.01, starter_threshold=5.0, bench_slope=0.012, bench_threshold=5.0)


def _tonight(decision):
    return {r.cell.player_id: r.cell for r in decision.recommendations}


def test_blowout_desactive_par_defaut():
    assert BLOWOUT_ENABLED is False


@pytest.mark.parametrize("over", [
    {},
    {"profiles": {1: _prof(1), 2: _prof(2, eff=1.2), 3: _prof(3, eff=1.0, minutes=18.0)}},
    {"picks": [PickRow(1, 1, TODAY + timedelta(days=20), "regular", "2026-27", False)]},
])
def test_blowout_absent_decision_strictement_identique(over):
    """Non-régression : sans modèle, des écarts attendus présents dans les
    entrées ne changent rien (projections, contextes, valeurs, plan)."""
    plain = decide(_inputs(**over))
    with_margins = decide(_inputs(expected_margins={"g1": 25.0, "g2": -25.0}, **over))
    assert with_margins == plain
    assert all(r.cell.ctx.expected_margin is None for r in plain.recommendations)


def test_blowout_active_titulaire_plus_bas_remplacant_plus_haut():
    profiles = {1: _prof(1), 2: _prof(2, eff=1.2), 3: _prof(3, eff=1.0, minutes=18.0)}
    margins = {"g1": 15.0, "g2": 0.0}   # DEN (domicile) favori de 15 pts ce soir
    plain = _tonight(decide(_inputs(profiles=profiles)))
    blow = _tonight(decide(_inputs(profiles=profiles, expected_margins=margins), blowout=BLOWOUT))
    assert blow[1].ctx.expected_margin == 15.0            # point de vue de DEN
    assert blow[2].ctx.expected_margin == -15.0           # point de vue de LAL
    assert blow[1].projection == pytest.approx(plain[1].projection * (1 - 0.01 * 10))
    assert blow[2].projection == pytest.approx(plain[2].projection * (1 - 0.01 * 10))
    assert blow[3].projection == pytest.approx(plain[3].projection * (1 + 0.012 * 10))


def test_blowout_active_match_sans_ecart_connu_inchange():
    plain = _tonight(decide(_inputs()))
    blow = _tonight(decide(_inputs(), blowout=BLOWOUT))   # aucun écart attendu dans les entrées
    assert {pid: c.projection for pid, c in blow.items()} == {pid: c.projection for pid, c in plain.items()}


# --- Blessés : Out + date de retour (correctif 2026-11, cas Edwards) -------

def test_plan_ecarte_un_joueur_out_avant_sa_date_de_retour():
    """Star DEN Out jusqu'à J+30 : le plan ne doit pas la placer à J+20,
    même avec un taux de présence de 0.95."""
    players = {**PLAYERS, 1: {**PLAYERS[1], "injury_status": "Out",
                              "injury_return_date": (TODAY + timedelta(days=30)).isoformat()}}
    d = decide(_inputs(players=players))
    assert all(e.cell.player_id != 1 for e in d.plan.values())
    assert all(r.cell.player_id != 1 for r in d.recommendations)


def test_plan_ecarte_un_joueur_de_retour_depuis_moins_de_7_jours():
    """Retour estimé à J+18 : à J+20 il n'est revenu que depuis 2 j, écarté."""
    players = {**PLAYERS, 1: {**PLAYERS[1], "injury_status": "Out",
                              "injury_return_date": (TODAY + timedelta(days=18)).isoformat()}}
    d = decide(_inputs(players=players))
    assert all(e.cell.player_id != 1 for e in d.plan.values())


# --- Pick du soir visible dans les recos (2026-11, cas Jokić) --------------

def _pick_tonight(pid=1):
    return [PickRow(99, pid, TODAY, "regular", "2026-27", False)]


def test_pick_du_soir_reste_dans_les_recos_marque():
    """Le cooldown de son propre pick l'excluait : Jokić pické ce soir
    disparaissait des recommandations."""
    d = decide(_inputs(picks=_pick_tonight()))
    star = next((r for r in d.recommendations if r.cell.player_id == 1), None)
    assert star is not None and star.is_pick
    assert all(not r.is_pick for r in d.recommendations if r.cell.player_id != 1)


def test_pick_du_soir_note_comme_sans_pick():
    """Même valeur (blocage de 30 j compris) que s'il n'était pas pické :
    sinon la comparaison avec les alternatives serait faussée."""
    free = next(r for r in decide(_inputs()).recommendations if r.cell.player_id == 1)
    picked = next(r for r in decide(_inputs(picks=_pick_tonight())).recommendations if r.cell.player_id == 1)
    assert picked.cell.value == pytest.approx(free.cell.value)
    assert picked.lock_value == pytest.approx(free.lock_value) and picked.lock_value > 0
    assert picked.best_future is not None and picked.best_future.night == TODAY + timedelta(days=20)


def test_pick_du_soir_pas_replanifie_plus_tard():
    d = decide(_inputs(picks=_pick_tonight()))
    later = d.plan.get(TODAY + timedelta(days=20))
    assert later is None or later.cell.player_id != 1


# --- Aucun risque le soir même (2026-11) ------------------------------------

def test_joueur_signale_ecarte_des_recos_du_soir():
    for status in ("Probable", "Day-To-Day", "Questionable"):
        players = {**PLAYERS, 1: {**PLAYERS[1], "injury_status": status}}
        d = decide(_inputs(players=players))
        assert 1 not in [r.cell.player_id for r in d.recommendations], status


def test_joueur_revenu_depuis_moins_de_7_jours_ecarte_ce_soir():
    back = {**PLAYERS[1], "injury_status": None, "injury_last_status": "Out",
            "injury_last_seen": (TODAY - timedelta(days=3)).isoformat()}
    d = decide(_inputs(players={**PLAYERS, 1: back}))
    assert 1 not in [r.cell.player_id for r in d.recommendations]
    healed = {**back, "injury_last_seen": (TODAY - timedelta(days=7)).isoformat()}
    d = decide(_inputs(players={**PLAYERS, 1: healed}))
    assert 1 in [r.cell.player_id for r in d.recommendations]


# --- Coéquipier majeur absent (2026-11) --------------------------------------
# DEN : joueur 1 (n°1, 51 pts de base) et joueur 5 (n°2, 40,8 pts).

MATE = {5: {"id": 5, "name": "Second DEN", "team": "DEN", "position": "G", "injury_status": None, "active": True}}


def _mate_inputs(star_status=None, second_status=None, shared=1.0, **over):
    base = _inputs()
    players = {**PLAYERS, **MATE, 1: {**PLAYERS[1], "injury_status": star_status},
               5: {**MATE[5], "injury_status": second_status}}
    args = dict(players=players, profiles={**base.profiles, 5: _prof(5, eff=1.2)},
                recent_logs={**base.recent_logs, 5: [{"minutes": 34}] * 3},
                team_leaders={"DEN": [1, 5], "LAL": [2]}, played_with={(5, 1): shared, (1, 5): shared, (3, 1): shared})
    args.update(over)
    return _inputs(**args)


def _proj(d, pid):
    return next(r.cell for r in d.recommendations if r.cell.player_id == pid)


def test_numero_1_absent_ses_coequipiers_projetes_plus_haut():
    normal = _proj(decide(_mate_inputs()), 5)
    without_star = _proj(decide(_mate_inputs(star_status="Out")), 5)
    assert without_star.projection == pytest.approx(normal.projection * 1.07)
    assert without_star.ctx.teammate_out == "Star DEN"


def test_numero_2_absent_pas_de_bonus_pour_le_numero_1():
    """Non vérifié hors échantillon (0,0 ± 0,8 sur 1 262 cas)."""
    normal = _proj(decide(_mate_inputs()), 1)
    assert _proj(decide(_mate_inputs(second_status="Out")), 1).projection == pytest.approx(normal.projection)


def test_pas_de_bonus_si_le_profil_contient_deja_l_absence():
    """Le n°1 manquait déjà tous les matchs récents du joueur : son profil a
    déjà monté, on ne compte pas l'effet deux fois."""
    normal = _proj(decide(_mate_inputs()), 5)
    assert _proj(decide(_mate_inputs(star_status="Out", shared=0.0)), 5).projection == pytest.approx(normal.projection)
    half = _proj(decide(_mate_inputs(star_status="Out", shared=0.5)), 5)
    assert half.projection == pytest.approx(normal.projection * 1.035)


def test_pas_de_bonus_sur_une_absence_incertaine():
    normal = _proj(decide(_mate_inputs()), 5)
    for status in ("Probable", "Day-To-Day", "Questionable", "Doubtful"):
        assert _proj(decide(_mate_inputs(star_status=status)), 5).projection == pytest.approx(normal.projection), status


def test_bonus_futur_seulement_avant_la_date_de_retour():
    later = TODAY + timedelta(days=20)
    star_back_soon = {"injury_status": "Out", "injury_return_date": (TODAY + timedelta(days=5)).isoformat()}
    star_out_long = {"injury_status": "Out", "injury_return_date": (TODAY + timedelta(days=40)).isoformat()}
    def plan_cell(star):
        inp = _mate_inputs()
        inp.players[1] = {**inp.players[1], **star}
        return decide(inp).plan[later].cell
    assert plan_cell(star_back_soon).ctx.teammate_factor == 1.0      # revenu d'ici là (lui reste en quarantaine)
    assert plan_cell(star_out_long).ctx.teammate_factor == pytest.approx(1.07)
