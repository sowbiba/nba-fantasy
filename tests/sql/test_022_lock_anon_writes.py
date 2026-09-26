def test_plus_aucune_ecriture_anon(pg):
    rows = pg.execute(
        "select tablename, policyname, cmd from pg_policies where schemaname = 'public' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast') and cmd <> 'SELECT'"
    ).fetchall()
    assert rows == []


def test_la_lecture_anon_reste(pg):
    tables = {t for (t,) in pg.execute(
        "select tablename from pg_policies where schemaname = 'public' and cmd = 'SELECT' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast')").fetchall()}
    assert tables == {"picks", "player_watchlist", "series_forecast"}
