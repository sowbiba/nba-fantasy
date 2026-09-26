import psycopg
import pytest


def _seed(pg):
    pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G')")
    pg.execute(
        "insert into games (id, date, home_team, away_team) values "
        "('0022600100', '2026-11-01', 'DEN', 'LAL'), ('0022600200', '2026-11-10', 'BOS', 'DEN'), "
        "('0022600300', '2026-11-12', 'PHX', 'LAL')"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "('2026-11-01', '2026-27', 'regular', 1, '2026-11-01T23:00:00Z'), "
        "('2026-11-10', '2026-27', 'regular', 1, '2026-11-10T23:00:00Z'), "
        "('2026-11-12', '2026-27', 'regular', 1, '2026-11-12T23:00:00Z')"
    )


def test_player_calendar_soirees_de_son_equipe_avec_dispo(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600100', '2026-11-01')")
        rows = pg.execute(
            "select night::text, opponent, is_home, ok, available_from::text, reason "
            "from player_calendar(1, '2026-11-01', '2026-11-30')"
        ).fetchall()
        assert rows == [
            ("2026-11-01", "LAL", True, False, "2026-12-01", "cooldown"),
            ("2026-11-10", "BOS", False, False, "2026-12-01", "cooldown"),
        ]   # le 12/11, DEN ne joue pas


def test_period_stats_soir_sans_pick_compte_zero_et_x2_double(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date, actual_score, is_x2) values "
                   "(1, '0022600100', '2026-11-01', 40, true)")
        row = pg.execute("select * from period_stats('2026-27', 'regular', '2026-11-11')").fetchone()
        # soirées 01/11 (80 avec le x2) et 10/11 (sans pick = 0) ; le 12/11 est après la borne
        assert row == (2, 2, 80, 40.0, 1, 0, 1)


def test_period_stats_pick_non_score_exclu(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (2, '0022600100', '2026-11-01')")
        nights, scored, total, average, *_ = pg.execute(
            "select * from period_stats('2026-27', 'regular', '2026-11-02')").fetchone()
        assert (nights, scored, total, average) == (1, 0, 0, None)


def test_plan_latest_ne_garde_que_le_dernier_plan(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into plan (generated_at, night, player_id, projection, p_play, value) values "
            "('2026-10-30T05:00:00Z', '2026-11-01', 1, 50, 1, 50), "
            "('2026-10-31T05:00:00Z', '2026-11-01', 2, 40, 1, 40)"
        )
        assert pg.execute("select player_id from plan_latest").fetchall() == [(2,)]


def test_x2_un_seul_par_mois(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0022600100', '2026-11-01', true)")
        with pytest.raises(psycopg.errors.UniqueViolation, match="picks_x2_month"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (2, '0022600200', '2026-11-10', true)")


def test_x2_interdit_hors_novembre_avril(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute("insert into games (id, date, home_team, away_team) values ('0022600010', '2026-10-25', 'DEN', 'LAL')")
        with pytest.raises(psycopg.errors.CheckViolation, match="picks_x2_window"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0022600010', '2026-10-25', true)")


def test_matchup_season(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into box_score_matchups_raw (game_id, off_player_id, def_player_id, def_team, def_player_name, "
            "matchup_seconds, player_points) values "
            "('0022600100', 1, 99, 'LAL', 'Davis', 600, 12), ('0022600100', 1, 98, 'LAL', 'James', 300, 5)"
        )
        rows = pg.execute(
            "select def_player_name, minutes, points, games from matchup_season "
            "where player_id = 1 and opponent_team = 'LAL' and season = '2026-27' order by minutes desc"
        ).fetchall()
        assert rows == [("Davis", 10, 12, 1), ("James", 5, 5, 1)]
