import psycopg
import pytest


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G')"
    )
    # Soirées passées et fermées de janvier (x2 autorisé), le 10 et le 11.
    for gid, day in (("0022600010", "2027-01-10"), ("0022600011", "2027-01-11")):
        pg.execute(
            "insert into games (id, date, home_team, away_team, game_type, season) values "
            "(%s, %s, 'DEN', 'LAC', 'regular', '2026-27')", (gid, day))
        pg.execute(
            "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
            "(%s, '2026-27', 'regular', 1, now() - interval '1 hour')", (day,))
    pg.execute("select set_config('ttfl.correction', 'on', true)")
    pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600010', '2027-01-10')")
    pg.execute("insert into picks (player_id, game_id, date) values (2, '0022600011', '2027-01-11')")
    pg.execute("select set_config('ttfl.correction', 'off', true)")


def test_correct_x2_active_et_retire_le_x2_soiree_fermee(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_x2('2027-01-10', true)")
        assert pg.execute("select is_x2 from picks where date = '2027-01-10'").fetchone() == (True,)
        pg.execute("select correct_x2('2027-01-10', false)")
        assert pg.execute("select is_x2 from picks where date = '2027-01-10'").fetchone() == (False,)


def test_x2_soiree_fermee_refuse_hors_correction(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            pg.execute("update picks set is_x2 = true where date = '2027-01-10'")


def test_correct_x2_garde_l_unicite_mensuelle(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_x2('2027-01-10', true)")
        with pytest.raises(psycopg.errors.UniqueViolation, match="picks_x2_month"):
            with pg.transaction():
                pg.execute("select correct_x2('2027-01-11', true)")


def test_correct_x2_sans_pick(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="no_pick"):
            pg.execute("select correct_x2('2027-01-12', true)")


def test_correct_x2_interdit_a_anon(pg):
    with pg.transaction(force_rollback=True):
        grants = pg.execute(
            "select has_function_privilege('anon', 'correct_x2(date, boolean)', 'execute')"
        ).fetchone()
        assert grants == (False,)
