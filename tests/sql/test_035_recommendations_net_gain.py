def test_recommendations_gain_net(pg):
    from decimal import Decimal
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'SGA', 'OKC', 'G'), "
                   "(2, 'Randle', 'MIN', 'F')")
        pg.execute("insert into recommendations (date, player_id, rank, estimated_score, tier, net_gain, net_gain_vs) "
                   "values ('2026-11-25', 1, 1, 40.9, 'elite', -4.8, 2)")
        assert pg.execute("select net_gain, net_gain_vs from recommendations").fetchone() == (Decimal("-4.8"), 2)
