import pathlib

import psycopg
import pytest

MIGRATION_018 = (
    pathlib.Path(__file__).parents[2] / "supabase" / "migrations" / "018_picks_availability.sql"
)


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values "
        "(1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G'), (3, 'LeBron', 'LAL', 'F')"
    )
    pg.execute(
        "insert into games (id, date, home_team, away_team) values "
        "('0022500100', '2025-10-25', 'DEN', 'LAL'), "
        "('0022500200', '2025-11-10', 'DEN', 'BOS'), "
        "('0022500300', '2025-11-24', 'DEN', 'PHX'), "
        "('0012600001', '2026-10-05', 'DEN', 'LAL'), "
        "('unknown_1_2025-11-12', '2025-11-12', 'DEN', 'UNK')"
    )


def test_trigger_remplit_mode_et_saison(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        assert pg.execute(
            "select mode, season from picks where date = '2025-10-25'"
        ).fetchone() == ("regular", "2025-26")


def test_trigger_refuse_cooldown(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        with pytest.raises(psycopg.errors.RaiseException, match="player_unavailable:cooldown"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500200', '2025-11-10')")


def test_trigger_accepte_j30(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500300', '2025-11-24')")


def test_trigger_refuse_match_ineligible(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_not_eligible:preseason"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0012600001', '2026-10-05')")
        with pytest.raises(psycopg.errors.RaiseException, match="night_not_eligible:unknown"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, 'unknown_1_2025-11-12', '2025-11-12')")


def test_trigger_refuse_joueur_absent_du_match(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="player_not_in_game"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (3, '0022500200', '2025-11-10')")


def test_trigger_refuse_date_incoherente(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="date_mismatch"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-26')")


def test_trigger_remplacement_meme_date(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500200', '2025-11-10')")
        # R2 : on remplace le joueur de la soirée, la ligne ne se bloque pas elle-même.
        pg.execute("update picks set player_id = 2 where date = '2025-11-10'")
        pg.execute("update picks set player_id = 1 where date = '2025-11-10'")


def test_trigger_ignore_maj_score(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        # Historique incohérent inséré sans validation (comme l'import 2025-26).
        pg.execute("set local session_replication_role = replica")
        pg.execute(
            "insert into picks (player_id, game_id, date, mode, season) values "
            "(1, '0022500100', '2025-10-25', 'regular', '2025-26'), "
            "(1, '0022500200', '2025-11-10', 'regular', '2025-26')"
        )
        pg.execute("set local session_replication_role = origin")
        # Le sync met à jour le score : aucune validation ne doit se déclencher.
        pg.execute("update picks set actual_score = 44, is_x2 = true where date = '2025-11-10'")


def test_backfill_x2_et_seconde_chance(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("set local session_replication_role = replica")
        pg.execute(
            "insert into picks (player_id, game_id, date, mode, estimated_score, actual_score) values "
            "(1, '0022500100', '2025-11-02', 'regular', 106, 53), "   # x2 réel
            "(2, '0022500200', '2025-11-12', 'regular', 0, 0), "      # zéro : jamais x2
            "(3, '0022500300', '2025-11-13', 'regular', 40, 38)"      # pick normal
        )
        pg.execute("set local session_replication_role = origin")
        pg.execute(MIGRATION_018.read_text())  # rejouer la migration applique les backfills
        rows = {
            d: (x2, est)
            for d, x2, est in pg.execute(
                "select date::text, is_x2, estimated_score from picks order by date"
            ).fetchall()
        }
        assert rows["2025-11-02"] == (True, None)
        assert rows["2025-11-12"] == (False, 0)
        assert rows["2025-11-13"] == (False, 40)
        assert pg.execute(
            "select bought_on::text, expires_on::text from second_chances"
        ).fetchall() == [("2025-11-17", "2025-11-24")]
