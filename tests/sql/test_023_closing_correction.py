import psycopg
import pytest


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values "
        "(1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G'), (3, 'Harden', 'LAC', 'G')"
    )
    # Soirée fermée (hier) et soirée ouverte (demain), relatives à now().
    pg.execute(
        "insert into games (id, date, home_team, away_team, game_type, season) values "
        "('0022600010', current_date - 1, 'DEN', 'LAC', 'regular', '2026-27'), "
        "('0022600020', current_date + 1, 'DEN', 'BOS', 'regular', '2026-27')"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "(current_date - 1, '2026-27', 'regular', 1, now() - interval '1 hour'), "
        "(current_date + 1, '2026-27', 'regular', 1, now() + interval '1 day')"
    )


def test_insert_refuse_apres_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600010', current_date - 1)")


def test_insert_accepte_avant_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600020', current_date + 1)")


def _pick_ferme(pg):
    pg.execute("select set_config('ttfl.correction', 'on', true)")
    pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600010', current_date - 1)")
    pg.execute("select set_config('ttfl.correction', 'off', true)")


def test_score_jamais_bloque(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        _pick_ferme(pg)
        pg.execute("update picks set actual_score = 42 where date = current_date - 1")
        assert pg.execute("select actual_score from picks where date = current_date - 1").fetchone() == (42,)


def test_changement_de_joueur_et_suppression_refuses_apres_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        _pick_ferme(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("update picks set player_id = 2 where date = current_date - 1")
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("update picks set is_x2 = true where date = current_date - 1")
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("delete from picks where date = current_date - 1")


def test_correct_pick_ajoute_remplace_supprime(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_pick(current_date - 1, 1)")
        assert pg.execute("select player_id, game_id from picks where date = current_date - 1").fetchone() == (1, "0022600010")
        pg.execute("update picks set actual_score = 30 where date = current_date - 1")
        pg.execute("select correct_pick(current_date - 1, 2)")
        assert pg.execute("select player_id, actual_score from picks where date = current_date - 1").fetchone() == (2, None)
        pg.execute("select correct_pick(current_date - 1, null)")
        assert pg.execute("select count(*) from picks where date = current_date - 1").fetchone() == (0,)


def test_correct_pick_respecte_le_cooldown(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600020', current_date + 1)")
        # La date corrigée (current_date - 1) précède le pick existant
        # (current_date + 1) : c'est le sens "réservé prochainement" de la
        # règle bidirectionnelle R3, donc reason=reserved_nearby et non
        # cooldown (qui ne s'applique qu'aux dates postérieures à un pick
        # existant). Le brief attendait "cooldown" ; corrigé ici pour
        # refléter le comportement réel de player_available_on (018).
        with pytest.raises(psycopg.errors.RaiseException, match="player_unavailable:reserved_nearby"):
            with pg.transaction():
                pg.execute("select correct_pick(current_date - 1, 1)")


def test_correct_pick_soiree_inconnue(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_unknown"):
            with pg.transaction():
                pg.execute("select correct_pick(current_date - 30, 1)")


def test_correct_pick_joueur_transfere_depuis(pg):
    """Harden jouait pour DEN ce soir-là (game_logs), il est à LAC aujourd'hui."""
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into game_logs (player_id, game_id, date, team, pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, "
            "ftm, fta, tov, minutes, ttfl_score, is_home, season) values "
            "(3, '0022600010', current_date - 1, 'DEN', 20, 5, 5, 1, 0, 8, 15, 2, 5, 2, 2, 3, 34, 25, true, '2026-27')"
        )
        pg.execute("update players set team = 'BOS' where id = 3")
        pg.execute("select correct_pick(current_date - 1, 3)")
        assert pg.execute("select player_id from picks where date = current_date - 1").fetchone() == (3,)


def test_correct_pick_interdit_a_anon(pg):
    with pg.transaction(force_rollback=True):
        grants = pg.execute(
            "select has_function_privilege('anon', 'correct_pick(date, integer)', 'execute')"
        ).fetchone()
        assert grants == (False,)
