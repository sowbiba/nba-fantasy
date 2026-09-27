"""029 — un match `final` aux scores nuls (glitch de données) est ignoré par
le classement : sa ligne ne doit pas occuper un rang dans la fenêtre des
10 derniers (last10). Même comportement que 027 sinon (colonnes/grants
inchangés)."""

from decimal import Decimal


def _seed(pg):
    # BOS bat NYK 10 fois d'affilée (0022600001..10), puis un 11e match
    # `final` mais aux scores nuls (glitch), le plus récent des 11.
    values = ", ".join(
        f"('00226000{str(n).zfill(2)}', '2026-11-{n:02d}', 'BOS', 'NYK', 'final', 100, 90)"
        for n in range(1, 11)
    )
    pg.execute(f"insert into games (id, date, home_team, away_team, status, home_score, away_score) values {values}")
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        "('0022600011', '2026-11-11', 'BOS', 'NYK', 'final', null, null)"
    )


def test_match_final_scores_nuls_ignore(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        bos = pg.execute(
            "select wins, losses, pct, last10_wins, last10_losses, streak "
            "from standings where team = 'BOS'"
        ).fetchone()
        # Sans le fix, le match aux scores nuls occupe quand même un rang
        # dans la fenêtre des 10 derniers (rn <= 10) et en exclut un vrai :
        # last10_wins tomberait à 9 au lieu de 10.
        assert bos == (10, 0, Decimal("1.000"), 10, 0, "V10")

        nyk_last10 = pg.execute(
            "select last10_wins, last10_losses from standings where team = 'NYK'"
        ).fetchone()
        assert nyk_last10 == (0, 10)
