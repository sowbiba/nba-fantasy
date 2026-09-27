import psycopg
import pytest


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values "
        "(1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G'), (3, 'Harden', 'LAC', 'G')"
    )
    pg.execute(
        "insert into games (id, date, home_team, away_team, game_type, season) values "
        "('0022600010', current_date - 1, 'DEN', 'LAC', 'regular', '2026-27')"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "(current_date - 1, '2026-27', 'regular', 1, now() - interval '1 hour')"
    )


def test_correct_pick_supprime_la_seconde_chance_du_pick_remplace(pg):
    # M8 (revue finale) : une Seconde chance est achetée sur un pick à 0,
    # donc elle appartient à ce joueur. Si correct_pick remplace le joueur
    # (synchro manuelle oubliée), la seconde chance ne doit pas rester
    # attachée au pick — elle disparaît avec le joueur qu'elle a rachetée.
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_pick(current_date - 1, 1)")
        pick_id = pg.execute("select id from picks where date = current_date - 1").fetchone()[0]
        pg.execute("update picks set actual_score = 0 where id = %s", (pick_id,))
        pg.execute(
            "insert into second_chances (pick_id, player_id, bought_on, expires_on) values "
            "(%s, 1, current_date, current_date + 3)",
            (pick_id,),
        )
        pg.execute("select correct_pick(current_date - 1, 2)")
        assert pg.execute("select count(*) from second_chances where pick_id = %s", (pick_id,)).fetchone() == (0,)
        assert pg.execute("select player_id, actual_score from picks where id = %s", (pick_id,)).fetchone() == (2, None)


def test_correct_pick_sans_seconde_chance_ne_plante_pas(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_pick(current_date - 1, 1)")
        pg.execute("select correct_pick(current_date - 1, 2)")
        assert pg.execute("select player_id from picks where date = current_date - 1").fetchone() == (2,)


def test_correct_pick_nouveau_pick_conserve_le_comportement_existant(pg):
    # Toujours pas de seconde chance à supprimer quand il n'y a pas encore
    # de pick pour cette soirée (insert, pas update).
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_pick(current_date - 1, 1)")
        assert pg.execute("select player_id, game_id from picks where date = current_date - 1").fetchone() == (1, "0022600010")


def test_correct_pick_interdit_a_anon(pg):
    with pg.transaction(force_rollback=True):
        grants = pg.execute(
            "select has_function_privilege('anon', 'correct_pick(date, integer)', 'execute')"
        ).fetchone()
        assert grants == (False,)
