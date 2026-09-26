"""Faux repo et fausses sources, en mémoire, pour tester les jobs sans réseau."""
from datetime import date


def _d(v):
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


class FakeRepo:
    def __init__(self, players=(), games=(), logs=(), picks=(), series=(), second_chances=()):
        self.players = {p["id"]: dict(p) for p in players}
        self.games = {g["id"]: dict(g) for g in games}
        self.logs = {(l["player_id"], l["game_id"]): dict(l) for l in logs}
        self.picks = [dict(p) for p in picks]
        self.series = list(series)
        self.second_chances = list(second_chances)
        self.nights = []
        self.recommendations = {}
        self.plan = []
        self.matchups = []
        self.inactive = set()

    # lectures
    def load_players(self):
        return list(self.players.values())

    def load_games_between(self, start, end):
        return [g for g in self.games.values() if start <= _d(g["date"]) <= end]

    def load_games_of_seasons(self, seasons):
        return [g for g in self.games.values() if g.get("season") in seasons]

    def load_game_logs(self, seasons):
        return [l for l in self.logs.values() if l.get("season") in seasons]

    def load_series(self, season):
        return [s for s in self.series if s.get("season") == season]

    def load_picks(self, season):
        return [p for p in self.picks if p.get("season") == season]

    def load_second_chances(self):
        return list(self.second_chances)

    def game_ids_with_logs(self, game_ids):
        return {gid for (_, gid) in self.logs} & set(game_ids)

    def game_ids_with_matchups(self, game_ids):
        return {m["game_id"] for m in self.matchups} & set(game_ids)

    # écritures
    def upsert_games(self, rows):
        from engine.rules.game_types import game_type_of, season_of
        for r in rows:
            g = {**self.games.get(r["id"], {"status": "scheduled"}), **r}
            g["game_type"] = game_type_of(g["id"])
            g["season"] = season_of(g["id"], _d(g["date"]))
            self.games[r["id"]] = g

    def upsert_players(self, rows):
        for r in rows:
            self.players[r["id"]] = {**self.players.get(r["id"], {"active": True}), **r}

    def upsert_game_logs(self, rows):
        for r in rows:
            missing = r["player_id"] not in self.players
            assert not missing, f"FK game_logs.player_id violée : {r['player_id']}"
            g = self.games[r["game_id"]]
            self.logs[(r["player_id"], r["game_id"])] = {**r, "season": g["season"]}

    def upsert_matchups_raw(self, rows):
        self.matchups.extend(rows)

    def set_inactive(self, ids):
        for pid in ids:
            self.players[pid]["active"] = False
            self.inactive.add(pid)

    def set_pick_score(self, pick_id, score):
        next(p for p in self.picks if p["id"] == pick_id)["actual_score"] = score

    def replace_nights(self, start, rows):
        self.nights = [n for n in self.nights if _d(n["date"]) < start] + list(rows)

    def replace_recommendations(self, night, rows):
        self.recommendations[night] = list(rows)

    def write_plan(self, rows, keep_since):
        self.plan = list(rows)


class FakeNbaSource:
    def __init__(self, schedule=(), scoreboard=(), box_scores=None, fail=False):
        self._schedule = list(schedule)
        self._scoreboard = list(scoreboard)
        self._box = box_scores or {}
        self.fail = fail

    def _maybe_fail(self):
        if self.fail:
            raise ConnectionError("NBA indisponible")

    def schedule(self, start, end):
        self._maybe_fail()
        return [g for g in self._schedule if start <= _d(g["date"]) <= end]

    def scoreboard(self, today):
        self._maybe_fail()
        return list(self._scoreboard)

    def box_score(self, game_id, game_date):
        self._maybe_fail()
        return list(self._box.get(game_id, []))
