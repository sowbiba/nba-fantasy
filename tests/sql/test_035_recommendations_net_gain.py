def test_recommendations_gain_net(pg):
    from decimal import Decimal
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'SGA', 'OKC', 'G'), "
                   "(2, 'Randle', 'MIN', 'F')")
        pg.execute("insert into recommendations (date, player_id, rank, estimated_score, tier, net_gain, net_gain_vs) "
                   "values ('2026-11-25', 1, 1, 40.9, 'elite', -4.8, 2)")
        assert pg.execute("select net_gain, net_gain_vs from recommendations").fetchone() == (Decimal("-4.8"), 2)


def test_une_seule_relation_recommendations_players(pg):
    """Une 2e clé vers players casse l'embed `players(name)` (PGRST201, 25/11/2026)."""
    n = pg.execute("select count(*) from information_schema.referential_constraints rc "
                   "join information_schema.table_constraints tc using (constraint_name) "
                   "where tc.table_name = 'recommendations'").fetchone()[0]
    assert n == 1
