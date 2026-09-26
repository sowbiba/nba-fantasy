import json
import pathlib

import pytest

CASES = json.loads(
    (pathlib.Path(__file__).parents[1] / "rules" / "availability_cases.json").read_text()
)


def _load_fixture(pg, case):
    # Mode réplica : désactive triggers et clés étrangères, pour n'insérer
    # que les lignes utiles au cas.
    pg.execute("set local session_replication_role = replica")
    for p in case["picks"]:
        pg.execute(
            "insert into picks (id, player_id, game_id, date, mode, season) "
            "values (%s, %s, 'fixture', %s, %s, %s)",
            (p["id"], p["player_id"], p["date"], p["mode"], p["season"]),
        )
    for s in case["second_chances"]:
        pg.execute(
            "insert into second_chances (pick_id, player_id, bought_on, expires_on) "
            "values (%s, %s, %s, %s)",
            (s["pick_id"], s["player_id"], s["bought_on"], s["expires_on"]),
        )
    for s in case["series"]:
        pg.execute(
            "insert into series (season, round, home_team, away_team, home_wins, away_wins, status) "
            "values (%(season)s, %(round)s, %(home_team)s, %(away_team)s, %(home_wins)s, %(away_wins)s, %(status)s)",
            s,
        )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_disponibilite_sql_identique_au_python(pg, case):
    with pg.transaction(force_rollback=True):
        _load_fixture(pg, case)
        ok, available_from, reason = pg.execute(
            "select ok, available_from, reason from player_available_on(%s, %s, %s, %s, %s, %s)",
            (case["player_id"], case["player_team"], case["night"], case["season"],
             case["mode"], case["exclude_pick_id"]),
        ).fetchone()
    exp = case["expected"]
    assert ok is exp["ok"]
    assert (available_from.isoformat() if available_from else None) == exp["available_from"]
    assert reason == exp["reason"]


def test_cooldown_days(pg):
    assert pg.execute("select cooldown_days()").fetchone() == (30,)
