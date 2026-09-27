from decimal import Decimal

EST_TEAMS = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL",
    "NYK", "ORL", "PHI", "TOR", "WAS",
}
OUEST_TEAMS = {
    "DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN", "NOP", "OKC",
    "PHX", "POR", "SAC", "SAS", "UTA",
}


def _seed(pg):
    # Saison fictive 2026-27 (id : préfixe 3 chiffres + année sur 2 chiffres,
    # cf. game_type_of/season_of de la migration 017).
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        # 3 matchs regular final : BOS bat NYK deux fois (dont un à l'extérieur), LAL bat DEN.
        "('0022600001', '2026-11-01', 'BOS', 'NYK', 'final', 100, 90), "
        "('0022600002', '2026-11-05', 'NYK', 'BOS', 'final', 95, 105), "
        "('0022600003', '2026-11-10', 'LAL', 'DEN', 'final', 110, 108), "
        # cup_final terminé : exclu du classement même si final.
        "('0062600004', '2026-12-15', 'BOS', 'NYK', 'final', 120, 100), "
        # preseason terminé : exclu.
        "('0012600005', '2026-10-01', 'LAL', 'DEN', 'final', 90, 80), "
        # regular non joué : ignoré (status scheduled par défaut).
        "('0022600006', '2026-11-20', 'DEN', 'LAL', 'scheduled', null, null), "
        # saison plus ancienne (2025-26, regular final) : ne doit pas polluer
        # la saison affichée (la plus récente = 2026-27).
        "('0022500099', '2025-11-01', 'MIA', 'ORL', 'final', 100, 90)"
    )


def test_toutes_les_equipes_presentes_est_ouest(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        rows = pg.execute("select team, conference from standings").fetchall()
        assert len(rows) == 30
        est = {t for t, c in rows if c == "Est"}
        ouest = {t for t, c in rows if c == "Ouest"}
        assert est == EST_TEAMS
        assert ouest == OUEST_TEAMS


def test_saison_affichee_est_la_plus_recente(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        seasons = {s for (s,) in pg.execute("select distinct season from standings").fetchall()}
        assert seasons == {"2026-27"}


def test_victoires_defaites_domicile_exterieur(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        bos = pg.execute(
            "select wins, losses, pct, home_wins, home_losses, away_wins, away_losses, "
            "last10_wins, last10_losses, streak from standings where team = 'BOS'"
        ).fetchone()
        assert bos == (2, 0, Decimal("1.000"), 1, 0, 1, 0, 2, 0, "V2")

        nyk = pg.execute(
            "select wins, losses, pct, home_wins, home_losses, away_wins, away_losses, streak "
            "from standings where team = 'NYK'"
        ).fetchone()
        assert nyk == (0, 2, Decimal("0.000"), 0, 1, 0, 1, "D2")

        lal = pg.execute(
            "select wins, losses, pct, home_wins, home_losses, away_wins, away_losses, streak "
            "from standings where team = 'LAL'"
        ).fetchone()
        assert lal == (1, 0, Decimal("1.000"), 1, 0, 0, 0, "V1")

        den = pg.execute(
            "select wins, losses, pct, home_wins, home_losses, away_wins, away_losses, streak "
            "from standings where team = 'DEN'"
        ).fetchone()
        assert den == (0, 1, Decimal("0.000"), 0, 0, 0, 1, "D1")


def test_equipe_sans_match_a_zero_partout_et_streak_vide(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        row = pg.execute(
            "select wins, losses, pct, home_wins, away_wins, last10_wins, streak "
            "from standings where team = 'MIA'"
        ).fetchone()
        # MIA n'a aucun match dans la saison 2026-27 (son seul match est en 2025-26).
        assert row == (0, 0, Decimal("0.000"), 0, 0, 0, "")


def test_cup_final_et_preseason_exclus(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        # BOS aurait 3 victoires si le cup_final comptait.
        wins, losses = pg.execute(
            "select wins, losses from standings where team = 'BOS'"
        ).fetchone()
        assert (wins, losses) == (2, 0)
        # LAL/DEN auraient un match de plus si le preseason comptait.
        lal_wins, den_losses = pg.execute(
            "select (select wins from standings where team = 'LAL'), "
            "(select losses from standings where team = 'DEN')"
        ).fetchone()
        assert (lal_wins, den_losses) == (1, 1)


def test_rank_et_games_behind_par_conference(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        bos_rank, bos_gb = pg.execute(
            "select rank, games_behind from standings where team = 'BOS'"
        ).fetchone()
        assert (bos_rank, bos_gb) == (1, Decimal("0"))

        nyk_gb = pg.execute("select games_behind from standings where team = 'NYK'").fetchone()[0]
        assert nyk_gb == Decimal("2")

        mia_gb = pg.execute("select games_behind from standings where team = 'MIA'").fetchone()[0]
        assert mia_gb == Decimal("1")

        lal_rank, lal_gb = pg.execute(
            "select rank, games_behind from standings where team = 'LAL'"
        ).fetchone()
        assert (lal_rank, lal_gb) == (1, Decimal("0"))

        den_gb = pg.execute("select games_behind from standings where team = 'DEN'").fetchone()[0]
        assert den_gb == Decimal("1")

        phx_gb = pg.execute("select games_behind from standings where team = 'PHX'").fetchone()[0]
        assert phx_gb == Decimal("0.5")

        ranks_est = [r for (r,) in pg.execute(
            "select rank from standings where conference = 'Est' order by rank"
        ).fetchall()]
        assert ranks_est == list(range(1, 16))
        ranks_ouest = [r for (r,) in pg.execute(
            "select rank from standings where conference = 'Ouest' order by rank"
        ).fetchall()]
        assert ranks_ouest == list(range(1, 16))


def test_anon_peut_lire_le_classement(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("set local role anon")
        rows = pg.execute("select team from standings").fetchall()
        pg.execute("reset role")
        assert len(rows) == 30
