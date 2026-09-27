"""028 — anon ne doit plus lire aucune donnée TTFL propre au joueur, ni
exécuter period_stats/player_calendar ; service_role continue de tout lire ;
games/players/nights/standings restent publics."""

PRIVATE_SELECTS = {
    "picks": "select * from picks",
    "second_chances": "select * from second_chances",
    "recommendations": "select * from recommendations",
    "plan": "select * from plan",
    "plan_latest": "select * from plan_latest",
    "player_watchlist": "select * from player_watchlist",
    "weekly_plan": "select * from weekly_plan",
    "series_forecast": "select * from series_forecast",
    "team_outlook": "select * from team_outlook",
    "player_team_rank": "select * from player_team_rank",
}

PUBLIC_SELECTS = {
    "games": "select * from games",
    "players": "select * from players",
    "nights": "select * from nights",
    "standings": "select * from standings",
}


def _seed(pg):
    pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        "('0022600001', '2026-11-01', 'DEN', 'LAL', 'final', 100, 90)"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "('2026-11-01', '2026-27', 'regular', 1, '2026-11-01T23:00:00Z')"
    )
    pg.execute("set local session_replication_role = replica")
    pg.execute(
        "insert into picks (player_id, game_id, date, mode, season, actual_score) values "
        "(1, '0022600001', '2026-11-01', 'regular', '2026-27', 45)"
    )
    pg.execute("set local session_replication_role = origin")
    pick_id = pg.execute("select id from picks limit 1").fetchone()[0]
    pg.execute(
        "insert into second_chances (pick_id, player_id, bought_on, expires_on) values "
        f"({pick_id}, 1, '2026-11-01', '2026-11-08')"
    )
    pg.execute(
        "insert into recommendations (date, player_id, rank, estimated_score, tier) values "
        "('2026-11-01', 1, 1, 50, 'S')"
    )
    pg.execute(
        "insert into plan (night, player_id, projection, p_play, value) values "
        "('2026-11-01', 1, 50, 1, 50)"
    )
    pg.execute("insert into player_watchlist (player_id, priority) values (1, 1)")
    pg.execute(
        "insert into weekly_plan (date, player_id, game_id, estimated_score) values "
        "('2026-11-01', 1, '0022600001', 50)"
    )
    pg.execute("insert into series (round, home_team, away_team) values (1, 'DEN', 'LAL')")
    series_id = pg.execute("select id from series limit 1").fetchone()[0]
    pg.execute(
        "insert into series_forecast (series_id, winner_team, expected_games) values "
        f"({series_id}, 'DEN', 6)"
    )
    pg.execute(
        "insert into team_outlook (team, outlook) values ('DEN', 'advance')"
    )
    pg.execute(
        "insert into player_team_rank (player_id, team, save_rank) values (1, 'DEN', 1)"
    )


def _rowcount_as_anon(pg, sql):
    """0 ligne (RLS sans policy permissive) ou erreur de permission : les
    deux sont des refus valides selon le brief de la tâche 2. Une erreur de
    permission avorte la transaction courante ; on l'encaisse dans une
    savepoint (pg.transaction() imbriquée) pour pouvoir continuer sur la
    même connexion ensuite (même motif que test_021_front_sr.py)."""
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


def test_donnees_ttfl_privees_illisibles_par_anon(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        for table, sql in PRIVATE_SELECTS.items():
            assert _rowcount_as_anon(pg, sql) == 0, f"{table} encore lisible par anon"


def test_donnees_publiques_restent_lisibles_par_anon(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        for table, sql in PUBLIC_SELECTS.items():
            assert _rowcount_as_anon(pg, sql) > 0, f"{table} devenu illisible par anon"


def test_period_stats_et_player_calendar_non_executables_par_anon(pg):
    with pg.transaction(force_rollback=True):
        row = pg.execute(
            "select has_function_privilege('anon', 'period_stats(text, text, date)', 'execute'), "
            "has_function_privilege('anon', 'player_calendar(int, date, date)', 'execute')"
        ).fetchone()
        assert row == (False, False)


def test_period_stats_et_player_calendar_executables_par_service_role(pg):
    with pg.transaction(force_rollback=True):
        row = pg.execute(
            "select has_function_privilege('service_role', 'period_stats(text, text, date)', 'execute'), "
            "has_function_privilege('service_role', 'player_calendar(int, date, date)', 'execute')"
        ).fetchone()
        assert row == (True, True)


def test_service_role_lit_tout(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("set local role service_role")
        try:
            for table, sql in {**PRIVATE_SELECTS, **PUBLIC_SELECTS}.items():
                rows = pg.execute(sql).fetchall()
                assert len(rows) > 0, f"service_role ne lit plus {table}"
        finally:
            pg.execute("reset role")
