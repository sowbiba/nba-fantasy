"""032 — `season_pronos` illisible par anon (RLS sans policy) ; contrainte
unique (season, name_key) ; vue publique `player_ttfl_season` correcte sur
données synthétiques (moyenne, top score avec date/adversaire, équipe du
dernier match après transfert, DNP et playin/preseason exclus) et lisible
par anon."""

import datetime
from decimal import Decimal

import pytest


def _rowcount_as_anon(pg, sql):
    """0 ligne (RLS sans policy permissive) ou erreur de permission : les
    deux sont des refus valides (même motif que test_028_private.py)."""
    pg.execute("set local role anon")
    n = 0
    try:
        with pg.transaction():
            rows = pg.execute(sql).fetchall()
            n = len(rows)
    except Exception:
        n = 0
    finally:
        pg.execute("reset role")
    return n


def test_anon_ne_lit_pas_season_pronos(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("set local session_replication_role = replica")
        pg.execute(
            "insert into season_pronos (season, name, name_key, wins, token_hash) values "
            "('2026-27', 'Ibra', 'ibra', '{}', 'x')"
        )
        pg.execute("set local session_replication_role = origin")
        assert _rowcount_as_anon(pg, "select * from season_pronos") == 0


def test_service_role_lit_season_pronos(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into season_pronos (season, name, name_key, wins, token_hash) values "
            "('2026-27', 'Ibra', 'ibra', '{}', 'x')"
        )
        pg.execute("set local role service_role")
        try:
            rows = pg.execute("select * from season_pronos").fetchall()
            assert len(rows) == 1
        finally:
            pg.execute("reset role")


def test_unique_season_name_key(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into season_pronos (season, name, name_key, wins, token_hash) values "
            "('2026-27', 'Ibra', 'ibra', '{}', 'x')"
        )
        with pytest.raises(Exception):
            with pg.transaction():
                pg.execute(
                    "insert into season_pronos (season, name, name_key, wins, token_hash) values "
                    "('2026-27', 'IBRA', 'ibra', '{}', 'y')"
                )


def test_updated_at_maintenu_par_trigger(pg):
    with pg.transaction(force_rollback=True):
        row = pg.execute(
            "insert into season_pronos (season, name, name_key, wins, token_hash) "
            "values ('2026-27', 'Ibra', 'ibra', '{}', 'x') "
            "returning id, created_at, updated_at"
        ).fetchone()
        pid, created_at, updated_at = row
        assert created_at == updated_at
        # Le client tente de forcer updated_at dans le passé : le trigger
        # doit l'écraser par now(), pas le laisser passer.
        forced_past = created_at - datetime.timedelta(days=1)
        pg.execute(
            "update season_pronos set wins = '{\"BOS\": 50}', "
            "updated_at = %s where id = %s",
            (forced_past, pid),
        )
        new_updated_at = pg.execute(
            "select updated_at from season_pronos where id = %s", (pid,)
        ).fetchone()[0]
        assert new_updated_at >= updated_at
        assert new_updated_at != forced_past


def _insert_player(pg, player_id, name, team):
    pg.execute(
        "insert into players (id, name, team, position) values (%s, %s, %s, 'F')",
        (player_id, name, team),
    )


def _insert_game(pg, game_id, date, home, away):
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) "
        "values (%s, %s, %s, %s, 'final', 100, 90)",
        (game_id, date, home, away),
    )


def _insert_log(pg, player_id, game_id, date, is_home, minutes, ttfl_score):
    pg.execute(
        "insert into game_logs (player_id, game_id, date, is_home, minutes, ttfl_score) "
        "values (%s, %s, %s, %s, %s, %s)",
        (player_id, game_id, date, is_home, minutes, ttfl_score),
    )


def _seed_view(pg):
    _insert_player(pg, 1, "Jokic", "DEN")

    # Trois matchs saison régulière (0022...) : DEN à domicile puis away
    # après un transfert vers BOS avant le dernier match. Top score = le
    # 2e match (45), date la plus ancienne en cas d'égalité (non testée
    # ici, cf. test dédié plus bas).
    _insert_game(pg, "0022600001", "2026-11-01", "DEN", "LAL")
    _insert_game(pg, "0022600002", "2026-11-03", "DEN", "MIA")
    _insert_game(pg, "0022600003", "2026-11-05", "BOS", "DEN")

    _insert_log(pg, 1, "0022600001", "2026-11-01", True, 30, 30)
    _insert_log(pg, 1, "0022600002", "2026-11-03", True, 32, 50)
    # DNP (minutes = 0) : exclu de la moyenne et du top.
    _insert_log(pg, 1, "0022600003", "2026-11-05", False, 0, 0)

    # Match playin (exclu de la vue) le même joueur, ne doit pas polluer
    # les agrégats regular ci-dessus.
    _insert_game(pg, "0052600001", "2026-04-15", "DEN", "GSW")
    _insert_log(pg, 1, "0052600001", "2026-04-15", True, 30, 60)

    # Match preseason (exclu) idem.
    _insert_game(pg, "0012600001", "2026-10-01", "DEN", "PHX")
    _insert_log(pg, 1, "0012600001", "2026-10-01", True, 20, 20)


def test_vue_moyenne_et_total(pg):
    with pg.transaction(force_rollback=True):
        _seed_view(pg)
        row = pg.execute(
            "select games, avg_ttfl, total_ttfl from player_ttfl_season "
            "where player_id = 1 and game_type = 'regular'"
        ).fetchone()
        # DNP exclu : 2 matchs (30, 50) -> moyenne 40.0, total 80.
        assert row == (2, Decimal("40.0"), 80)


def test_vue_playin_et_preseason_exclus(pg):
    with pg.transaction(force_rollback=True):
        _seed_view(pg)
        rows = pg.execute(
            "select game_type from player_ttfl_season where player_id = 1"
        ).fetchall()
        game_types = {r[0] for r in rows}
        assert game_types == {"regular"}


def test_vue_equipe_du_dernier_match(pg):
    with pg.transaction(force_rollback=True):
        _seed_view(pg)
        # DNP au 3e match (BOS, minutes=0) : le dernier match *joué* (>0
        # minutes) est le 2e, toujours avec DEN. On ajoute un 4e match joué
        # avec BOS pour vérifier que l'équipe suit le dernier match joué.
        _insert_game(pg, "0022600004", "2026-11-07", "BOS", "MIA")
        _insert_log(pg, 1, "0022600004", "2026-11-07", True, 25, 20)
        team = pg.execute(
            "select team from player_ttfl_season where player_id = 1 and game_type = 'regular'"
        ).fetchone()[0]
        assert team == "BOS"


def test_vue_top_score_date_et_adversaire(pg):
    with pg.transaction(force_rollback=True):
        _seed_view(pg)
        top_score, top_date, top_opponent = pg.execute(
            "select top_score, top_date, top_opponent from player_ttfl_season "
            "where player_id = 1 and game_type = 'regular'"
        ).fetchone()
        assert top_score == 50
        assert str(top_date) == "2026-11-03"
        # DEN à domicile le 2026-11-03 contre MIA -> adversaire = MIA.
        assert top_opponent == "MIA"


def test_vue_top_score_egalite_date_plus_ancienne(pg):
    with pg.transaction(force_rollback=True):
        _insert_player(pg, 2, "Murray", "DEN")
        _insert_game(pg, "0022600010", "2026-11-01", "DEN", "LAL")
        _insert_game(pg, "0022600011", "2026-11-02", "DEN", "MIA")
        _insert_log(pg, 2, "0022600010", "2026-11-01", True, 30, 40)
        _insert_log(pg, 2, "0022600011", "2026-11-02", True, 30, 40)
        top_date, top_opponent = pg.execute(
            "select top_date, top_opponent from player_ttfl_season "
            "where player_id = 2 and game_type = 'regular'"
        ).fetchone()
        assert str(top_date) == "2026-11-01"
        assert top_opponent == "LAL"


def test_anon_lit_la_vue(pg):
    with pg.transaction(force_rollback=True):
        _seed_view(pg)
        assert _rowcount_as_anon(pg, "select * from player_ttfl_season") > 0
