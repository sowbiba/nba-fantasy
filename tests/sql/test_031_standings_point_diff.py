"""031 — nouvelle colonne publique `point_diff` (écart moyen de points par
match) sur la vue `standings` : même périmètre de matchs que 029 (saison
régulière, `status = 'final'`, scores non nuls), arrondi à 1 décimale, 0 sans
match joué. `create or replace view` n'ajoute une colonne qu'en dernière
position : les colonnes existantes doivent rester dans le même ordre."""

from decimal import Decimal


def _seed_bos_nyk(pg):
    # BOS bat NYK 10 fois d'affilée 100-90 (+10 pour BOS, -10 pour NYK), puis
    # un 11e match `final` mais aux scores nuls (glitch, cf. 029) : ne doit
    # pas entrer dans la moyenne.
    values = ", ".join(
        f"('00226000{str(n).zfill(2)}', '2026-11-{n:02d}', 'BOS', 'NYK', 'final', 100, 90)"
        for n in range(1, 11)
    )
    pg.execute(f"insert into games (id, date, home_team, away_team, status, home_score, away_score) values {values}")
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        "('0022600011', '2026-11-11', 'BOS', 'NYK', 'final', null, null)"
    )


def test_ecart_moyen_pour_contre(pg):
    with pg.transaction(force_rollback=True):
        _seed_bos_nyk(pg)
        bos = pg.execute("select point_diff from standings where team = 'BOS'").fetchone()
        assert bos == (Decimal("10.0"),)
        nyk = pg.execute("select point_diff from standings where team = 'NYK'").fetchone()
        assert nyk == (Decimal("-10.0"),)


def test_match_nul_exclu_de_la_moyenne(pg):
    # Le 11e match ('final' mais scores nuls) doit être exclu du dénominateur
    # de la moyenne. S'il comptait pour 0 (glitch traité comme un match nul
    # 0-0), la moyenne de BOS tomberait à 100*10/11 = 90.9, arrondie à 90.9,
    # au lieu de 100.0 sur les 10 vrais matchs.
    with pg.transaction(force_rollback=True):
        _seed_bos_nyk(pg)
        bos = pg.execute("select point_diff from standings where team = 'BOS'").fetchone()
        assert bos == (Decimal("10.0"),)
        assert bos != (Decimal("9.1"),)


def test_arrondi_a_une_decimale(pg):
    with pg.transaction(force_rollback=True):
        # +7, +6, +6 -> moyenne 6.333... arrondie à 6.3
        pg.execute(
            "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
            "('0022600021', '2026-11-01', 'BOS', 'NYK', 'final', 107, 100), "
            "('0022600022', '2026-11-02', 'BOS', 'NYK', 'final', 106, 100), "
            "('0022600023', '2026-11-03', 'BOS', 'NYK', 'final', 106, 100)"
        )
        bos = pg.execute("select point_diff from standings where team = 'BOS'").fetchone()
        assert bos == (Decimal("6.3"),)


def test_zero_sans_match_joue(pg):
    with pg.transaction(force_rollback=True):
        bos = pg.execute("select point_diff from standings where team = 'BOS'").fetchone()
        assert bos == (Decimal("0"),)


def test_colonnes_existantes_inchangees_point_diff_en_dernier(pg):
    with pg.transaction(force_rollback=True):
        cols = pg.execute(
            "select column_name from information_schema.columns "
            "where table_name = 'standings' order by ordinal_position"
        ).fetchall()
        assert [c[0] for c in cols] == [
            "season",
            "conference",
            "team",
            "wins",
            "losses",
            "pct",
            "games_behind",
            "home_wins",
            "home_losses",
            "away_wins",
            "away_losses",
            "last10_wins",
            "last10_losses",
            "streak",
            "rank",
            "point_diff",
        ]
