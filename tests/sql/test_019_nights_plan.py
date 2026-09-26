def test_player_availability_par_soiree(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into players (id, name, team, position, active) values "
            "(1, 'Jokic', 'DEN', 'C', true), (2, 'Murray', 'DEN', 'G', true), "
            "(3, 'Retraite', 'DEN', 'F', false)"
        )
        pg.execute(
            "insert into games (id, date, home_team, away_team) values "
            "('0022600100', '2026-10-25', 'DEN', 'LAL'), ('0022600200', '2026-11-10', 'DEN', 'BOS')"
        )
        pg.execute(
            "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
            "('2026-11-10', '2026-27', 'regular', 1, '2026-11-10T23:00:00Z')"
        )
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600100', '2026-10-25')")
        rows = {
            r[0]: r[1:]
            for r in pg.execute(
                "select player_id, ok, available_from::text, reason "
                "from player_availability('2026-11-10') order by player_id"
            ).fetchall()
        }
        assert rows == {
            1: (False, "2026-11-24", "cooldown"),
            2: (True, None, None),
        }  # le joueur inactif n'apparaît pas


def test_player_availability_soiree_inconnue(pg):
    assert pg.execute("select count(*) from player_availability('2030-01-01')").fetchone() == (0,)


def test_plan_insertion(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute(
            "insert into plan (night, player_id, is_x2, projection, p_play, value, explanation) "
            "values ('2026-11-10', 1, false, 52.0, 0.95, 49.4, 'match facile à domicile')"
        )
        assert pg.execute("select count(*) from plan").fetchone() == (1,)
