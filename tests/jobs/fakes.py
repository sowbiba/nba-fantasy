"""Faux repo et fausses sources, en mémoire, pour tester les jobs sans réseau.

Les méthodes d'écriture valident colonnes autorisées / NOT NULL, en miroir
du schéma réel, pour détecter à l'exécution des tests ce qui casserait en
prod (colonne inconnue, valeur manquante) plutôt qu'en silence.
"""
from datetime import date

PLAYERS_ALLOWED = {
    "id", "name", "team", "position", "injury_status", "injury_detail", "injury_short_comment",
    "injury_return_date", "injury_updated_at", "avg_ttfl_l5", "avg_ttfl_l10", "avg_ttfl_l20",
    "avg_ttfl_season", "stddev_ttfl", "home_avg", "away_avg", "avg_minutes_l10", "usage_rate",
    "updated_at", "active",
}
PLAYERS_NOT_NULL = {"id", "name", "team", "position"}

GAMES_ALLOWED = {
    "id", "date", "home_team", "away_team", "tip_off", "status", "home_score", "away_score",
    "series_id", "game_number", "game_type", "season",
}
GAMES_NOT_NULL = {"id", "date", "home_team", "away_team"}

GAME_LOGS_ALLOWED = {
    "player_id", "game_id", "date", "season", "team", "pts", "reb", "ast", "stl", "blk", "fgm",
    "fga", "tpm", "tpa", "ftm", "fta", "tov", "fouls", "minutes", "ttfl_score", "is_home",
}
GAME_LOGS_NOT_NULL = {"player_id", "game_id", "date"}

RECOMMENDATIONS_ALLOWED = {
    "date", "player_id", "rank", "estimated_score", "perf_score", "matchup_score", "strategy_score",
    "pros", "cons", "verdict", "tier", "tags", "computed_at", "projection", "p_play", "value",
    "lock_value", "locked_until", "best_future",
}
RECOMMENDATIONS_NOT_NULL = {"date", "player_id", "rank", "estimated_score", "tier"}

NIGHTS_ALLOWED = {"date", "season", "mode", "n_eligible_games", "closing_at", "is_phantom", "updated_at"}
NIGHTS_NOT_NULL = {"date", "season", "mode", "n_eligible_games", "closing_at"}
NIGHT_MODES = {"regular", "playoffs"}

PLAN_ALLOWED = {"generated_at", "night", "player_id", "is_x2", "projection", "p_play", "value", "explanation"}
PLAN_NOT_NULL = {"generated_at", "night", "player_id", "is_x2", "projection", "p_play", "value"}

MATCHUPS_ALLOWED = {
    "game_id", "off_player_id", "def_player_id", "off_team", "def_team", "series_id",
    "off_player_name", "def_player_name", "matchup_seconds", "partial_possessions", "player_points",
    "matchup_assists", "matchup_turnovers", "matchup_blocks", "matchup_fgm", "matchup_fga",
    "matchup_tpm", "matchup_tpa", "matchup_ftm", "matchup_fta",
}
MATCHUPS_NOT_NULL = {"game_id", "off_player_id", "def_player_id"}


def _d(v):
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _validate(rows, allowed, not_null, table):
    for r in rows:
        extra = set(r) - allowed
        assert not extra, f"{table} : colonne(s) non autorisée(s) {extra}"
        missing = [k for k in not_null if r.get(k) is None]
        assert not missing, f"{table} : colonne(s) NOT NULL manquante(s) {missing}"


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
        _validate(rows, GAMES_ALLOWED, GAMES_NOT_NULL, "games")
        for r in rows:
            g = {**self.games.get(r["id"], {"status": "scheduled"}), **r}
            g["game_type"] = game_type_of(g["id"])
            g["season"] = season_of(g["id"], _d(g["date"]))
            self.games[r["id"]] = g

    def upsert_players(self, rows):
        _validate(rows, PLAYERS_ALLOWED, PLAYERS_NOT_NULL, "players")
        for r in rows:
            self.players[r["id"]] = {**self.players.get(r["id"], {"active": True}), **r}

    def upsert_game_logs(self, rows):
        _validate(rows, GAME_LOGS_ALLOWED, GAME_LOGS_NOT_NULL, "game_logs")
        for r in rows:
            missing = r["player_id"] not in self.players
            assert not missing, f"FK game_logs.player_id violée : {r['player_id']}"
            g = self.games[r["game_id"]]
            self.logs[(r["player_id"], r["game_id"])] = {**r, "season": g["season"]}

    def upsert_matchups_raw(self, rows):
        _validate(rows, MATCHUPS_ALLOWED, MATCHUPS_NOT_NULL, "box_score_matchups_raw")
        self.matchups.extend(rows)

    def set_inactive(self, ids):
        for pid in ids:
            self.players[pid]["active"] = False
            self.inactive.add(pid)

    def set_pick_score(self, pick_id, score):
        next(p for p in self.picks if p["id"] == pick_id)["actual_score"] = score

    def replace_nights(self, start, rows):
        _validate(rows, NIGHTS_ALLOWED, NIGHTS_NOT_NULL, "nights")
        bad_mode = [r["mode"] for r in rows if r["mode"] not in NIGHT_MODES]
        assert not bad_mode, f"nights : mode(s) invalide(s) {bad_mode}"
        self.nights = [n for n in self.nights if _d(n["date"]) < start] + list(rows)

    def replace_recommendations(self, night, rows):
        _validate(rows, RECOMMENDATIONS_ALLOWED, RECOMMENDATIONS_NOT_NULL, "recommendations")
        player_ids = [r["player_id"] for r in rows]
        assert len(player_ids) == len(set(player_ids)), "recommendations : player_id dupliqué dans le même replace"
        self.recommendations[night] = list(rows)

    def write_plan(self, rows, keep_since):
        _validate(rows, PLAN_ALLOWED, PLAN_NOT_NULL, "plan")
        keys = [(r["generated_at"], r["night"]) for r in rows]
        assert len(keys) == len(set(keys)), "plan : (generated_at, night) dupliqué"
        self.plan = list(rows)


class FakeStatsSource:
    def __init__(self, rosters=None, game_logs=None, matchups=None, fail_teams=(), schedule=None):
        self._rosters = rosters or {}
        self._logs = game_logs or {}
        self._matchups = matchups or {}
        self._schedule = list(schedule or [])
        self.fail_teams = set(fail_teams)
        self.log_calls = []
        self.roster_calls = []
        self.schedule_calls = []

    def roster(self, team_id, tricode, season):
        self.roster_calls.append((team_id, tricode, season))
        if tricode in self.fail_teams:
            raise ConnectionError("roster KO")
        return list(self._rosters.get(tricode, []))

    def league_game_log(self, season, season_type, date_from=None):
        self.log_calls.append((season, season_type, date_from))
        return self._logs.get((season, season_type), ({}, [], {}))

    def matchups(self, game_id):
        return list(self._matchups.get(game_id, []))

    def schedule_stats(self, season, start, end):
        self.schedule_calls.append((season, start, end))
        return [g for g in self._schedule if start.isoformat() <= g["date"] <= end.isoformat()]
