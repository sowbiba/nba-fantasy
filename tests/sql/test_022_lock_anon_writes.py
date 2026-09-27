def test_plus_aucune_ecriture_anon(pg):
    rows = pg.execute(
        "select tablename, policyname, cmd from pg_policies where schemaname = 'public' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast') and cmd <> 'SELECT'"
    ).fetchall()
    assert rows == []


def test_la_lecture_anon_ne_reste_plus_apres_028(pg):
    # Vrai juste après 022 (022 ne touchait qu'aux écritures), mais 028
    # (mode public : données TTFL privées) retire ensuite ces mêmes
    # policies de lecture. La suite tourne toujours sur la chaîne complète
    # de migrations, donc l'état constaté ici est celui d'après 028.
    tables = {t for (t,) in pg.execute(
        "select tablename from pg_policies where schemaname = 'public' and cmd = 'SELECT' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast')").fetchall()}
    assert tables == set()
