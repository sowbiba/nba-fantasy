"""030 — team_elo et game_predictions : RLS sans policy (aucune lecture
anon), service_role lit tout, contrainte de probabilité sur
home_win_prob."""

PRIVATE_SELECTS = {
    "team_elo": "select * from team_elo",
    "game_predictions": "select * from game_predictions",
}


def _seed(pg):
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        "('0022600001', '2026-11-01', 'DEN', 'LAL', 'final', 100, 90)"
    )
    pg.execute("insert into team_elo (team, rating, games) values ('DEN', 1520.5, 10)")
    pg.execute(
        "insert into game_predictions (game_id, home_rating, away_rating, home_win_prob, expected_margin) "
        "values ('0022600001', 1520.5, 1490.0, 0.62, 4.5)"
    )


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


def test_anon_ne_lit_ni_elo_ni_predictions(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        for table, sql in PRIVATE_SELECTS.items():
            assert _rowcount_as_anon(pg, sql) == 0, f"{table} lisible par anon"


def test_service_role_lit_tout(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("set local role service_role")
        try:
            for table, sql in PRIVATE_SELECTS.items():
                rows = pg.execute(sql).fetchall()
                assert len(rows) > 0, f"service_role ne lit plus {table}"
        finally:
            pg.execute("reset role")


def test_home_win_prob_contrainte_entre_0_et_1(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
            "('0022600002', '2026-11-02', 'BOS', 'MIA', 'final', 110, 100)"
        )
        try:
            with pg.transaction():
                pg.execute(
                    "insert into game_predictions (game_id, home_rating, away_rating, home_win_prob, "
                    "expected_margin) values ('0022600002', 1500, 1500, 1.5, 0)"
                )
            raised = False
        except Exception:
            raised = True
        assert raised, "home_win_prob hors [0, 1] aurait dû violer la contrainte"


def test_game_predictions_reference_games(pg):
    with pg.transaction(force_rollback=True):
        try:
            with pg.transaction():
                pg.execute(
                    "insert into game_predictions (game_id, home_rating, away_rating, home_win_prob, "
                    "expected_margin) values ('does_not_exist', 1500, 1500, 0.5, 0)"
                )
            raised = False
        except Exception:
            raised = True
        assert raised, "game_predictions aurait dû refuser un game_id inexistant"
