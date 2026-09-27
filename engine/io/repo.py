"""Accès Supabase du moteur.

Toute lecture multi-lignes est paginée (PostgREST plafonne à 1000 lignes
par requête : audit §2) et toute écriture de masse part par lots de 500.
"""
from datetime import UTC, date, datetime
from typing import Callable, Iterable

PAGE = 1000
CHUNK = 500


class SupabaseRepo:
    def __init__(self, client):
        self.c = client

    @classmethod
    def from_env(cls) -> "SupabaseRepo":
        from supabase import create_client

        from engine.config import env
        return cls(create_client(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY")))

    # --- mécanique -------------------------------------------------------
    def _all(self, make_query: Callable) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            chunk = make_query().range(offset, offset + PAGE - 1).execute().data or []
            rows.extend(chunk)
            if len(chunk) < PAGE:
                return rows
            offset += PAGE

    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        for i in range(0, len(rows), CHUNK):
            self.c.table(table).upsert(rows[i:i + CHUNK], on_conflict=on_conflict).execute()

    def _ids_present(self, table: str, game_ids: Iterable[str]) -> set[str]:
        ids = sorted(set(game_ids))
        if not ids:
            return set()
        found: set[str] = set()
        for i in range(0, len(ids), 100):
            part = ids[i:i + 100]
            rows = self._all(lambda: self.c.table(table).select("id,game_id").in_("game_id", part).order("id"))
            found |= {r["game_id"] for r in rows}
        return found

    # --- lectures --------------------------------------------------------
    def load_players(self) -> list[dict]:
        return self._all(lambda: self.c.table("players").select("*").order("id"))

    def load_games_between(self, start: date, end: date) -> list[dict]:
        return self._all(lambda: self.c.table("games").select("*")
                         .gte("date", start.isoformat()).lte("date", end.isoformat()).order("id"))

    def load_games_of_seasons(self, seasons: list[str]) -> list[dict]:
        return self._all(lambda: self.c.table("games")
                         .select("id,date,home_team,away_team,game_type,season,status,tip_off,"
                                 "home_score,away_score")
                         .in_("season", seasons).order("id"))

    def load_game_logs(self, seasons: list[str]) -> list[dict]:
        return self._all(lambda: self.c.table("game_logs")
                         .select("player_id,game_id,date,season,team,minutes,ttfl_score,is_home")
                         .in_("season", seasons).order("id"))

    def load_series(self, season: str) -> list[dict]:
        return self._all(lambda: self.c.table("series").select("*").eq("season", season).order("id"))

    def load_picks(self, season: str) -> list[dict]:
        return self._all(lambda: self.c.table("picks")
                         .select("id,player_id,game_id,date,mode,season,actual_score,is_x2")
                         .eq("season", season).order("id"))

    def load_second_chances(self) -> list[dict]:
        return self._all(lambda: self.c.table("second_chances")
                         .select("pick_id,player_id,bought_on,expires_on").order("id"))

    def game_ids_with_logs(self, game_ids: Iterable[str]) -> set[str]:
        return self._ids_present("game_logs", game_ids)

    def game_ids_with_matchups(self, game_ids: Iterable[str]) -> set[str]:
        return self._ids_present("box_score_matchups_raw", game_ids)

    # --- écritures -------------------------------------------------------
    def upsert_games(self, rows: list[dict]) -> None:
        self._upsert("games", rows, "id")

    def upsert_players(self, rows: list[dict]) -> None:
        self._upsert("players", rows, "id")

    def upsert_game_logs(self, rows: list[dict]) -> None:
        self._upsert("game_logs", rows, "player_id,game_id")

    def upsert_matchups_raw(self, rows: list[dict]) -> None:
        self._upsert("box_score_matchups_raw", rows, "game_id,off_player_id,def_player_id")

    def upsert_team_elo(self, rows: list[dict]) -> None:
        self._upsert("team_elo", rows, "team")

    def upsert_game_predictions(self, rows: list[dict]) -> None:
        self._upsert("game_predictions", rows, "game_id")

    def set_inactive(self, player_ids: Iterable[int]) -> None:
        ids = sorted(set(player_ids))
        for i in range(0, len(ids), 100):
            self.c.table("players").update({"active": False}).in_("id", ids[i:i + 100]).execute()

    def set_pick_score(self, pick_id: int, score: int) -> None:
        self.c.table("picks").update({"actual_score": score}).eq("id", pick_id).execute()

    def upsert_nights(self, rows: list[dict]) -> None:
        self._upsert("nights", rows, "date")

    def replace_nights(self, start: date, rows: list[dict]) -> None:
        # Upsert d'abord, purge des soirées obsolètes ensuite : un échec de
        # l'écriture ne doit jamais laisser la soirée du jour sans ligne
        # `nights` (le guard de fermeture et les rappels en dépendent).
        if rows:
            self.c.table("nights").upsert(rows, on_conflict="date").execute()
        kept = {r["date"] for r in rows}
        q = self.c.table("nights").delete().gte("date", start.isoformat())
        if kept:
            q = q.not_.in_("date", list(kept))
        q.execute()

    def replace_recommendations(self, night: date, rows: list[dict]) -> None:
        self.c.table("recommendations").delete().eq("date", night.isoformat()).execute()
        if rows:
            self.c.table("recommendations").insert(rows).execute()

    def write_plan(self, rows: list[dict], keep_since: datetime) -> None:
        if rows:
            self.c.table("plan").insert(rows).execute()
        self.c.table("plan").delete().lt("generated_at", keep_since.isoformat()).execute()

    # --- journal ---------------------------------------------------------
    def start_log(self, job: str) -> int:
        res = self.c.table("sync_log").insert({
            "job": job, "status": "running", "started_at": datetime.now(UTC).isoformat(),
        }).execute()
        return res.data[0]["id"]

    def finish_log(self, log_id: int, *, status: str, players_updated: int = 0,
                   error: str | None = None, api_calls: dict | None = None) -> None:
        self.c.table("sync_log").update({
            "status": status,
            "finished_at": datetime.now(UTC).isoformat(),
            "players_updated": players_updated,
            "error_message": (error or "")[:500] or None,
            "api_calls": api_calls or {},
        }).eq("id", log_id).execute()
