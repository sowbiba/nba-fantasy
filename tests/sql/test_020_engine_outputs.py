def test_recommendations_colonnes_s1(pg):
    from decimal import Decimal
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute(
            "insert into recommendations (date, player_id, rank, estimated_score, tier, "
            "projection, p_play, value, lock_value, locked_until, best_future) values "
            "('2026-11-10', 1, 1, 49.4, 'elite', 52.0, 0.95, 47.1, 38.0, '2026-12-10', 'jeudi 20 vs WAS')"
        )
        assert pg.execute("select value, locked_until::text from recommendations").fetchone() == (Decimal("47.1"), "2026-12-10")


def test_sync_log_job_et_api_calls(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into sync_log (status) values ('running')")
        assert pg.execute("select job, api_calls from sync_log").fetchone() == ("daily_sync", {})
