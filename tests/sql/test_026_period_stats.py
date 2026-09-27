from decimal import Decimal

import psycopg
import pytest


def _seed(pg):
    pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G')")
    pg.execute(
        "insert into games (id, date, home_team, away_team) values "
        "('0022600101', '2026-11-01', 'DEN', 'LAL'), "  # nuit éligible, pick à 0
        "('0022600102', '2026-11-03', 'DEN', 'MIA'), "   # aucune ligne nights (hors saison éligible)
        "('0022600103', '2026-11-05', 'DEN', 'PHX'), "   # nuit éligible, pick x2
        "('0022600104', '2026-11-08', 'DEN', 'GSW'), "   # nuit éligible, sans pick
        "('0022600105', '2026-12-20', 'DEN', 'SAC')"     # x2 futur réservé (mois différent de novembre)
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "('2026-11-01', '2026-27', 'regular', 1, '2026-11-01T23:00:00Z'), "
        "('2026-11-05', '2026-27', 'regular', 1, '2026-11-05T23:00:00Z'), "
        "('2026-11-08', '2026-27', 'regular', 1, '2026-11-08T23:00:00Z')"
    )
    # Le joueur 2 (Murray) doit rester libre : on ne lui insère aucun pick
    # pour tester player_calendar sur un joueur sans historique.
    # Les picks sont tous rapprochés dans le temps (< 30j, R3) : on bypass le
    # trigger de validation comme l'import historique (test_018), en fixant
    # nous-mêmes mode/season.
    pg.execute("set local session_replication_role = replica")
    pg.execute(
        "insert into picks (player_id, game_id, date, mode, season, actual_score, is_x2) values "
        "(1, '0022600101', '2026-11-01', 'regular', '2026-27', 0, false), "     # pick à 0
        "(1, '0022600102', '2026-11-03', 'regular', '2026-27', 0, false), "     # hors nights : ne doit pas compter (ni dans picks, ni dans zeros)
        "(1, '0022600103', '2026-11-05', 'regular', '2026-27', 40, true), "     # x2 du mois de novembre
        "(1, '0022600105', '2026-12-20', 'regular', '2026-27', null, true)"     # x2 réservé, futur : pas encore joué
    )
    pg.execute("set local session_replication_role = origin")


def test_period_stats_borne_p_until_et_soirees_eligibles(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        row = pg.execute("select * from period_stats('2026-27', 'regular', '2026-11-10')").fetchone()
        # nuits éligibles < p_until : 01/11 (0), 05/11 (40*2=80), 08/11 (sans pick = 0)
        # le pick du 03/11 (hors nights) et le x2 réservé du 20/12 (>= p_until) sont exclus
        assert row == (3, 3, 80, Decimal("26.7"), 2, 1, 1)


def test_player_calendar_joueur_libre_ok_true(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into games (id, date, home_team, away_team) values ('0022600200', '2026-11-15', 'DEN', 'BOS')")
        pg.execute(
            "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
            "('2026-11-15', '2026-27', 'regular', 1, '2026-11-15T23:00:00Z')"
        )
        rows = pg.execute(
            "select ok, available_from, reason from player_calendar(2, '2026-11-15', '2026-11-15')"
        ).fetchall()
        assert rows == [(True, None, None)]


def test_x2_interdit_en_mai(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute("insert into games (id, date, home_team, away_team) values ('0022600300', '2026-05-15', 'DEN', 'LAL')")
        with pytest.raises(psycopg.errors.CheckViolation, match="picks_x2_window"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0022600300', '2026-05-15', true)")


def test_x2_interdit_en_playoffs(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute("insert into games (id, date, home_team, away_team) values ('0042600110', '2026-11-15', 'DEN', 'LAL')")
        with pytest.raises(psycopg.errors.CheckViolation, match="picks_x2_window"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0042600110', '2026-11-15', true)")
