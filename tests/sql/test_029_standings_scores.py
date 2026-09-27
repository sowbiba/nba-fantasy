"""029 — un match `final` aux scores nuls (glitch de données) est ignoré par
le classement : ni V/D, ni pollution du rang des 10 derniers ou de la
série. Même comportement que 027 sinon (colonnes/grants inchangés)."""

from decimal import Decimal


def _seed(pg):
    pg.execute(
        "insert into games (id, date, home_team, away_team, status, home_score, away_score) values "
        # 2 victoires BOS normales.
        "('0022600001', '2026-11-01', 'BOS', 'NYK', 'final', 100, 90), "
        "('0022600002', '2026-11-05', 'BOS', 'NYK', 'final', 105, 95), "
        # match `final` mais scores nuls (glitch) : ignoré malgré le statut.
        "('0022600003', '2026-11-10', 'BOS', 'NYK', 'final', null, null)"
    )


def test_match_final_scores_nuls_ignore(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        bos = pg.execute(
            "select wins, losses, pct, last10_wins, last10_losses, streak "
            "from standings where team = 'BOS'"
        ).fetchone()
        # Sans le fix, le 3e match compterait dans last10 (rn) et casserait
        # la série V2 (won = null coupe le groupe de streak).
        assert bos == (2, 0, Decimal("1.000"), 2, 0, "V2")

        nyk = pg.execute(
            "select wins, losses, last10_wins, last10_losses "
            "from standings where team = 'NYK'"
        ).fetchone()
        assert nyk == (0, 2, 0, 2)
