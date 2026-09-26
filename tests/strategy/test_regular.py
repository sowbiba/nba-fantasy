from datetime import date, datetime, timedelta

from engine.rules.availability import PickRow
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


def test_decide_lock_value_et_meilleur_futur():
    d = decide(_inputs())
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.best_future is not None and star.best_future.night == TODAY + timedelta(days=20)
    assert star.lock_value > 0
    assert star.locked_until == TODAY + timedelta(days=30)


def test_decide_plan_joue_la_star_a_son_meilleur_soir():
    d = decide(_inputs())
    assert d.plan[TODAY + timedelta(days=20)].player_id == 1
    assert d.plan[TODAY].player_id == 2


def test_decide_exclut_cooldown_et_out():
    players = {**PLAYERS, 2: {**PLAYERS[2], "injury_status": "Out"}}
    picks = [PickRow(9, 1, TODAY - timedelta(days=10), "regular", "2026-27")]
    d = decide(_inputs(players=players, picks=picks))
    assert [r.cell.player_id for r in d.recommendations] == []


def test_decide_respecte_les_reservations():
    resa = PickRow(7, 1, TODAY + timedelta(days=20), "regular", "2026-27")
    d = decide(_inputs(picks=[resa]))
    assert TODAY + timedelta(days=20) not in d.plan          # soirée déjà fixée
    assert 1 not in [r.cell.player_id for r in d.recommendations]   # réservé à J+20 → bloqué ce soir


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
