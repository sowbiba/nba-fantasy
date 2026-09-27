from datetime import UTC, date, datetime, timedelta

import pytest

from engine.jobs.daily_sync import apply_scoreboard, game_prediction_rows, run, team_elo_rows
from engine.stats.elo import EloParams
from tests.jobs.fakes import FakeRepo

TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def _player(pid, team, pos="G", **k):
    return {"id": pid, "name": f"Joueur {pid}", "team": team, "position": pos,
            "injury_status": None, "active": True, **k}


def _log(pid, gid, d, team, minutes=34, ttfl=50, season="2026-27", home=True):
    return {"player_id": pid, "game_id": gid, "date": d.isoformat(), "season": season, "team": team,
            "minutes": minutes, "ttfl_score": ttfl, "is_home": home}


def _base_repo(**over):
    players = [_player(1, "DEN", "C"), _player(2, "LAL"), _player(3, "BOS")]
    past = TODAY - timedelta(days=2)
    yesterday = TODAY - timedelta(days=1)
    games = [
        {"id": "0022600010", "date": past.isoformat(), "home_team": "DEN", "away_team": "LAL",
         "status": "final", "game_type": "regular", "season": "2026-27"},
        {"id": "0022600011", "date": yesterday.isoformat(), "home_team": "BOS",
         "away_team": "DEN", "status": "final", "game_type": "regular", "season": "2026-27"},
        # Déjà en base (chargé par local_nightly, calendrier stats.nba.com) :
        # daily_sync ne fait plus que rafraîchir statut/score via ESPN.
        {"id": "0022600020", "date": TODAY.isoformat(), "home_team": "DEN", "away_team": "LAL",
         "status": "scheduled", "game_type": "regular", "season": "2026-27",
         "tip_off": "2026-11-03T01:00:00Z"},
    ]
    logs = [_log(1, "0022600010", past, "DEN"), _log(2, "0022600010", past, "LAL", ttfl=35, home=False),
            _log(3, "0022600011", yesterday, "BOS", ttfl=44)]
    # Saison précédente : sans prior, un seul match courant laisse le profil
    # proche du rookie (< 15 min attendues) et personne ne serait candidat.
    for pid, team in ((1, "DEN"), (2, "LAL"), (3, "BOS")):
        logs += [_log(pid, f"prior{pid}{i}", date(2026, 3, 1) + timedelta(days=i), team, season="2025-26")
                 for i in range(5)]
    picks = [{"id": 1, "player_id": 3, "game_id": "0022600011", "date": yesterday.isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": False}]
    kwargs = dict(players=players, games=games, logs=logs, picks=picks)
    kwargs.update(over)
    return FakeRepo(**kwargs)


def _fetch_scoreboard(rows_by_date):
    """Fausse `fetch_scoreboard(d)` : retourne les lignes ESPN de la date `d`."""
    def fetch(d):
        return list(rows_by_date.get(d.isoformat(), []))
    return fetch


SCOREBOARD = {
    (TODAY - timedelta(days=1)).isoformat(): [
        {"date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "BOS", "away_team": "DEN",
         "tip_off": "2026-11-02T00:00Z", "status": "final", "home_score": 101, "away_score": 99},
    ],
    TODAY.isoformat(): [
        {"date": TODAY.isoformat(), "home_team": "DEN", "away_team": "LAL",
         "tip_off": "2026-11-03T01:00:00Z", "status": "scheduled", "home_score": None, "away_score": None},
    ],
}


def test_daily_sync_de_bout_en_bout():
    repo = _base_repo()
    result = run(repo, _fetch_scoreboard(SCOREBOARD), lambda: {}, TODAY, NOW)
    # le calendrier (games) vient déjà de la base (chargé par local_nightly) ;
    # daily_sync ne fait plus que rafraîchir statut/score via ESPN.
    assert [n["date"] for n in repo.nights] == [TODAY.isoformat()]
    assert repo.games["0022600011"]["home_score"] == 101 and repo.games["0022600011"]["away_score"] == 99
    # pick scoré depuis les logs déjà en base (chargés par local_nightly)
    assert repo.picks[0]["actual_score"] == 44
    recs = repo.recommendations[TODAY]
    assert result.recommendations == len(recs) > 0
    assert {"projection", "p_play", "value", "lock_value", "locked_until", "best_future",
            "estimated_score", "rank", "tier", "pros", "cons", "verdict", "tags"} <= set(recs[0])
    assert recs[0]["rank"] == 1
    assert repo.plan and all(r["generated_at"] == NOW.isoformat() for r in repo.plan)


def test_daily_sync_continue_si_nba_indisponible():
    def boom(d):
        raise ConnectionError("ESPN indisponible")
    repo = _base_repo()
    result = run(repo, boom, lambda: {}, TODAY, NOW)
    assert result.warnings                # étapes réseau notées, pas d'exception
    assert repo.recommendations[TODAY]   # la décision tourne sur les données en base


def test_daily_sync_blessures():
    repo = _base_repo()
    injuries = {"LAL": [{"name": "Joueur 2", "status": "Out", "detail": "Genou", "return_date": None,
                         "short_comment": "", "updated_at": ""}]}
    run(repo, _fetch_scoreboard(SCOREBOARD), lambda: injuries, TODAY, NOW)
    assert repo.players[2]["injury_status"] == "Out"
    assert 2 not in [r["player_id"] for r in repo.recommendations[TODAY]]


def test_daily_sync_n_ingere_pas_un_match_en_cours():
    # Le run 07:00 Paris (01:00 ET) voit encore en direct certains matchs de
    # la veille finis tard aux USA : pas de scoring du pick tant que ce n'est
    # ni "final" ni assez ancien pour être sûrement terminé.
    repo = _base_repo()
    repo.games["0022600011"]["status"] = "live"
    result = run(repo, _fetch_scoreboard({}), lambda: {}, TODAY, NOW)
    assert repo.picks[0]["actual_score"] is None
    assert result is not None


def test_daily_sync_match_ancien_non_final_score_le_pick():
    # Un match d'il y a 2 jours ou plus est nécessairement terminé, même si
    # son statut n'a jamais été rafraîchi à "final" côté NBA : le pick est
    # scoré à partir du log déjà chargé par local_nightly.
    players = [_player(1, "DEN", "C"), _player(2, "LAL"), _player(3, "BOS")]
    d2 = TODAY - timedelta(days=2)
    games = [
        {"id": "0022600012", "date": d2.isoformat(), "home_team": "BOS", "away_team": "DEN",
         "status": "scheduled", "game_type": "regular", "season": "2026-27"},
    ]
    logs = [_log(3, "0022600012", d2, "BOS", ttfl=40)]
    for pid, team in ((1, "DEN"), (2, "LAL"), (3, "BOS")):
        logs += [_log(pid, f"prior{pid}{i}", date(2026, 3, 1) + timedelta(days=i), team, season="2025-26")
                 for i in range(5)]
    picks = [{"id": 1, "player_id": 3, "game_id": "0022600012", "date": d2.isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": False}]
    repo = FakeRepo(players=players, games=games, logs=logs, picks=picks)
    run(repo, _fetch_scoreboard({}), lambda: {}, TODAY, NOW)
    assert repo.picks[0]["actual_score"] == 40


def test_score_picks_rescore_un_pick_vieux_de_60_jours():
    # I1 : une correction (correct_pick) peut porter sur une soirée ancienne
    # (actual_score remis à null) ; la synchro suivante doit la rescorer même
    # si le match a plus de 40 jours (spec §3.1 : "recalculé par la synchro
    # suivante").
    old = TODAY - timedelta(days=60)
    players = [_player(1, "DEN", "C")]
    games = [{"id": "0022600099", "date": old.isoformat(), "home_team": "DEN", "away_team": "LAL",
              "status": "final", "game_type": "regular", "season": "2026-27"}]
    logs = [_log(1, "0022600099", old, "DEN", ttfl=37)]
    picks = [{"id": 1, "player_id": 1, "game_id": "0022600099", "date": old.isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": False}]
    repo = FakeRepo(players=players, games=games, logs=logs, picks=picks)
    run(repo, _fetch_scoreboard({}), lambda: {}, TODAY, NOW)
    assert repo.picks[0]["actual_score"] == 37


def test_scoreboard_espn_apparie_par_date_et_equipes():
    game = {"id": "0022600001", "date": "2026-10-20", "home_team": "DET", "away_team": "BOS",
            "status": "scheduled", "game_type": "regular", "season": "2026-27"}
    repo = FakeRepo(games=[game])
    rows = [{"date": "2026-10-20", "home_team": "DET", "away_team": "BOS", "tip_off": "2026-10-20T19:00Z",
             "status": "final", "home_score": 101, "away_score": 99},
            {"date": "2026-10-20", "home_team": "XXX", "away_team": "YYY", "tip_off": None,
             "status": "final", "home_score": 1, "away_score": 2}]
    assert apply_scoreboard(repo, rows, [game]) == 1
    stored = repo.games["0022600001"]
    assert (stored["status"], stored["home_score"], stored["away_score"]) == ("final", 101, 99)


def test_daily_sync_n_appelle_plus_le_cdn():
    calls = []
    run(FakeRepo(), lambda d: calls.append(d) or [], lambda: {}, TODAY, NOW)
    assert calls == [TODAY - timedelta(days=1), TODAY]   # journée US d'hier et d'aujourd'hui


def test_fake_repo_matchups_raw_exige_def_player_id():
    # box_score_matchups_raw : game_id, off_player_id, def_player_id NOT NULL
    # (migration 013) — une ligne sans def_player_id doit être rejetée.
    with pytest.raises(AssertionError):
        FakeRepo().upsert_matchups_raw([{"game_id": "g", "off_player_id": 1}])


def test_daily_sync_ecrit_le_x2_du_plan():
    # Seule soirée de novembre visible = ce soir → x2 de novembre forcé (S3).
    repo = _base_repo()
    run(repo, _fetch_scoreboard(SCOREBOARD), lambda: {}, TODAY, NOW)
    assert [(r["night"], r["is_x2"]) for r in repo.plan] == [(TODAY.isoformat(), True)]


def test_daily_sync_ecrit_l_elo_des_equipes():
    repo = _base_repo()
    run(repo, _fetch_scoreboard(SCOREBOARD), lambda: {}, TODAY, NOW)
    # Seul "0022600011" (BOS-DEN, hier) a un score connu (via le scoreboard
    # ESPN de ce run) : "0022600010" (DEN-LAL, il y a 2 jours) n'en a jamais
    # reçu dans cette fixture, donc n'est pas comptable par l'Elo — LAL n'a
    # encore aucune ligne `team_elo`.
    assert set(repo.team_elo) == {"DEN", "BOS"}
    assert repo.team_elo["DEN"]["games"] == 1
    assert repo.team_elo["BOS"]["games"] == 1
    for row in repo.team_elo.values():
        assert row["updated_at"] == NOW.isoformat()
        assert isinstance(row["rating"], float)


def test_daily_sync_ecrit_les_predictions_de_match_a_venir():
    repo = _base_repo()
    run(repo, _fetch_scoreboard(SCOREBOARD), lambda: {}, TODAY, NOW)
    # Seul le match de ce soir (DEN-LAL, "scheduled") est dans la fenêtre à
    # venir et non terminé : les matchs déjà "final" n'ont pas de prédiction.
    assert set(repo.game_predictions) == {"0022600020"}
    pred = repo.game_predictions["0022600020"]
    assert 0.0 <= pred["home_win_prob"] <= 1.0
    assert pred["updated_at"] == NOW.isoformat()


def test_game_prediction_rows_hors_fenetre_ou_matchs_termines_ignores():
    games = [
        {"id": "past", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "LAL",
         "away_team": "DEN", "status": "final"},
        {"id": "loin", "date": (TODAY + timedelta(days=20)).isoformat(), "home_team": "LAL",
         "away_team": "DEN", "status": "scheduled"},
        {"id": "ok", "date": TODAY.isoformat(), "home_team": "LAL", "away_team": "DEN", "status": "scheduled"},
    ]
    rows = game_prediction_rows(games, TODAY, {"LAL": 1500.0, "DEN": 1500.0}, {}, EloParams(), NOW)
    assert [r["game_id"] for r in rows] == ["ok"]


def test_game_prediction_rows_joueur_out_baisse_la_probabilite_de_son_equipe():
    # Correction blessures activée (elo_per_share > 0) : la part d'absents de
    # l'équipe à domicile (LAL) baisse sa note et donc sa probabilité de
    # victoire, par rapport à la même situation sans correction.
    game = {"id": "g1", "date": TODAY.isoformat(), "home_team": "LAL", "away_team": "DEN", "status": "scheduled"}
    ratings = {"LAL": 1550.0, "DEN": 1550.0}
    absent = {"LAL": 0.6}
    rows_no_injury = game_prediction_rows([game], TODAY, ratings, absent, EloParams(elo_per_share=0.0), NOW)
    rows_injury = game_prediction_rows([game], TODAY, ratings, absent, EloParams(elo_per_share=200.0), NOW)
    assert rows_no_injury[0]["home_win_prob"] > rows_injury[0]["home_win_prob"]
    assert 0.0 <= rows_injury[0]["home_win_prob"] <= 1.0


def test_team_elo_rows_note_arrondie_et_compte_les_matchs_comptables():
    games = [
        {"id": "1", "date": (TODAY - timedelta(days=2)).isoformat(), "home_team": "LAL", "away_team": "DEN",
         "status": "final", "home_score": 100, "away_score": 90, "game_type": "regular", "season": "2026-27"},
        {"id": "2", "date": TODAY.isoformat(), "home_team": "LAL", "away_team": "DEN", "status": "scheduled",
         "game_type": "regular", "season": "2026-27"},
    ]
    ratings = {"LAL": 1512.345, "DEN": 1487.655}
    rows = team_elo_rows(games, TODAY, ratings, NOW)
    by_team = {r["team"]: r for r in rows}
    assert by_team["LAL"]["games"] == 1 and by_team["DEN"]["games"] == 1   # le match du soir ne compte pas encore
    assert by_team["LAL"]["rating"] == round(1512.345, 2)


def test_daily_sync_pas_de_x2_si_le_mois_est_deja_servi():
    yesterday = TODAY - timedelta(days=1)
    picks = [{"id": 1, "player_id": 3, "game_id": "0022600011", "date": yesterday.isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": True}]
    repo = _base_repo(picks=picks)
    run(repo, _fetch_scoreboard(SCOREBOARD), lambda: {}, TODAY, NOW)
    assert repo.plan and not any(r["is_x2"] for r in repo.plan)
