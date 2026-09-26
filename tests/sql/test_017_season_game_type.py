import json
import pathlib

import pytest

CASES = json.loads(
    (pathlib.Path(__file__).parents[1] / "rules" / "game_type_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_game_type_sql_identique_au_python(pg, case):
    row = pg.execute(
        "select game_type_of(%s), season_of(%s, %s::date)",
        (case["id"], case["id"], case["date"]),
    ).fetchone()
    assert row == (case["game_type"], case["season"])


def test_trigger_games_remplit_type_et_saison(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into games (id, date, home_team, away_team) "
            "values ('0012600007', '2026-10-05', 'DEN', 'LAL')"
        )
        row = pg.execute(
            "select game_type, season from games where id = '0012600007'"
        ).fetchone()
        assert row == ("preseason", "2026-27")


def test_trigger_game_logs_equipe_au_moment_du_match(pg):
    # Joueur transféré depuis : game_logs.team garde l'équipe du match,
    # pas l'équipe actuelle de players.team.
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'X', 'BOS', 'G')")
        pg.execute(
            "insert into games (id, date, home_team, away_team) "
            "values ('0022500050', '2025-11-01', 'DEN', 'LAL')"
        )
        pg.execute(
            "insert into game_logs (player_id, game_id, date, is_home) "
            "values (1, '0022500050', '2025-11-01', false)"
        )
        row = pg.execute(
            "select team, season from game_logs where game_id = '0022500050'"
        ).fetchone()
        assert row == ("LAL", "2025-26")


def test_colonnes_prod_declarees(pg):
    cols = {
        (t, c)
        for t, c in pg.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public'"
        ).fetchall()
    }
    for expected in [
        ("games", "home_score"), ("games", "away_score"),
        ("players", "injury_short_comment"), ("players", "injury_return_date"),
        ("players", "injury_updated_at"), ("players", "active"),
        ("series", "season"),
    ]:
        assert expected in cols
