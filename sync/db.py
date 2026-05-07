# sync/db.py
"""Supabase read/write layer for the sync backend.

Uses the service_role key for full write access.
"""
from datetime import UTC, date, datetime
from supabase import create_client, Client
from sync.config import SUPABASE_URL, SUPABASE_SERVICE_KEY


def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# --- Sync log ---

def start_sync_log(client: Client) -> int:
    result = client.table("sync_log").insert({
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
    }).execute()
    return result.data[0]["id"]


def finish_sync_log(client: Client, log_id: int, players_updated: int):
    client.table("sync_log").update({
        "finished_at": datetime.now(UTC).isoformat(),
        "status": "success",
        "players_updated": players_updated,
    }).eq("id", log_id).execute()


def fail_sync_log(client: Client, log_id: int, error: str):
    client.table("sync_log").update({
        "finished_at": datetime.now(UTC).isoformat(),
        "status": "error",
        "error_message": error[:500],
    }).eq("id", log_id).execute()


# --- Players ---

def upsert_players(client: Client, players: list[dict]):
    """Upsert player rows. Each dict must have 'id' key."""
    if not players:
        return
    client.table("players").upsert(players, on_conflict="id").execute()


# --- Games ---

def upsert_games(client: Client, games: list[dict]):
    if not games:
        return
    client.table("games").upsert(games, on_conflict="id").execute()


# --- Series ---

def upsert_series(client: Client, series_list: list[dict]):
    if not series_list:
        return
    client.table("series").upsert(series_list, on_conflict="id").execute()


# --- Game logs ---

def upsert_game_logs(client: Client, logs: list[dict]):
    if not logs:
        return
    client.table("game_logs").upsert(
        logs, on_conflict="player_id,game_id"
    ).execute()


# --- Team defense ---

def upsert_team_defense(client: Client, defense: list[dict]):
    if not defense:
        return
    client.table("team_defense").upsert(defense, on_conflict="team").execute()


# --- Recommendations ---

def replace_recommendations(client: Client, recs: list[dict], target_date: date):
    """Delete existing recs for the date and insert new ones."""
    client.table("recommendations").delete().eq(
        "date", target_date.isoformat()
    ).execute()
    if recs:
        client.table("recommendations").insert(recs).execute()


# --- Picks ---

def get_picks(client: Client, mode: str = "playoffs") -> list[dict]:
    result = client.table("picks").select("*").eq("mode", mode).order("date", desc=True).execute()
    return result.data


def get_picked_player_ids(client: Client, mode: str = "playoffs") -> set[int]:
    picks = get_picks(client, mode)
    return {p["player_id"] for p in picks}


def insert_pick(client: Client, pick: dict):
    client.table("picks").insert(pick).execute()


def update_pick_actual_score(client: Client, pick_date: date, actual_score: int):
    client.table("picks").update({
        "actual_score": actual_score,
    }).eq("date", pick_date.isoformat()).execute()


# --- Read helpers (used by scoring) ---

def get_player_game_logs(client: Client, player_id: int, limit: int = 20) -> list[dict]:
    result = client.table("game_logs").select("*").eq(
        "player_id", player_id
    ).order("date", desc=True).limit(limit).execute()
    return result.data


def get_today_games(client: Client, today: date) -> list[dict]:
    # Drop games belonging to a completed series (phantom G6/G7 from a
    # series that ended early — the static NBA schedule keeps the
    # placeholder slots and we keep upserting them, but they will never
    # be played). Match both by series_id AND by team pair, since
    # seed_playoffs.py only links games whose gameLabel still carries the
    # round name; conditional games sometimes lose that label once the
    # series clinches and end up with series_id=NULL.
    completed = client.table("series").select(
        "id,home_team,away_team"
    ).eq("status", "completed").execute().data or []
    completed_ids = {row["id"] for row in completed}
    completed_pairs = {
        tuple(sorted((row["home_team"], row["away_team"]))) for row in completed
    }
    result = client.table("games").select("*").eq("date", today.isoformat()).execute()
    out = []
    for g in result.data:
        # Real played games (final/live) are kept even if their series is now
        # marked completed — Game 7 of a 4-3 series legitimately belongs to a
        # completed series. Only `scheduled` placeholders are phantoms.
        is_played = g.get("status") in ("final", "live")
        if not is_played:
            if g.get("series_id") and g["series_id"] in completed_ids:
                continue
            pair = tuple(sorted((g["home_team"], g["away_team"])))
            if pair in completed_pairs:
                continue
        out.append(g)
    return out


def get_active_series(client: Client) -> list[dict]:
    result = client.table("series").select("*").eq("status", "active").execute()
    return result.data


def get_team_defense(client: Client, team: str) -> dict | None:
    result = client.table("team_defense").select("*").eq("team", team).execute()
    return result.data[0] if result.data else None


def get_all_players(client: Client) -> list[dict]:
    result = client.table("players").select("*").execute()
    return result.data


def get_latest_sync(client: Client) -> dict | None:
    result = client.table("sync_log").select("*").order(
        "started_at", desc=True
    ).limit(1).execute()
    return result.data[0] if result.data else None
