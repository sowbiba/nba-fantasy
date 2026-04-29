"""One-shot backfill: re-fetch box scores for recent final games and
upsert them, so that DNP rows (minutes == "PT00M") land in game_logs now
that the fetcher keeps them.

Previously `fetch_live_box_score` dropped DNPs; their absence inflated
bench-player averages (a single garbage-time outlier would dominate the
L5/L10 signal). Run this after deploying the updated fetcher to refresh
history:

    python -m sync.backfill_dnp --days 60

Then re-run the normal sync so player aggregates are recomputed from the
fresh logs.
"""
import argparse
from datetime import UTC, date, datetime, timedelta

from sync import db
from sync.fetcher import fetch_live_box_score, compute_player_aggregates


def backfill(days: int = 60) -> None:
    client = db.get_client()
    today = date.today()
    start = today - timedelta(days=days)

    games = (
        client.table("games").select("id, date, status, home_team")
        .gte("date", start.isoformat()).lte("date", today.isoformat())
        .eq("status", "final")
        .order("date").execute().data
    ) or []
    print(f"{len(games)} final games in the window [{start} → {today}]")

    # Restrict inserts to players that already exist in the DB. The box
    # score occasionally contains two-way / 10-day contract players whose
    # ids are not in our roster, which would trip the FK constraint.
    known_player_ids = {
        row["id"] for row in client.table("players").select("id").execute().data or []
    }
    print(f"{len(known_player_ids)} known player ids")

    touched_player_ids: set[int] = set()
    for g in games:
        box_players = fetch_live_box_score(
            g["id"],
            home_tricode=g.get("home_team"),
            game_date=g.get("date"),
        )
        if not box_players:
            print(f"  {g['date']} · {g['id']} · no box score returned (skip)")
            continue
        box_players = [bp for bp in box_players if bp["player_id"] in known_player_ids]
        if not box_players:
            print(f"  {g['date']} · {g['id']} · no known players in box (skip)")
            continue
        rows = [
            {
                "player_id": bp["player_id"],
                "game_id": bp["game_id"],
                "date": bp["date"],
                "pts": bp["pts"], "reb": bp["reb"], "ast": bp["ast"],
                "stl": bp["stl"], "blk": bp["blk"],
                "fgm": bp["fgm"], "fga": bp["fga"],
                "tpm": bp["tpm"], "tpa": bp["tpa"],
                "ftm": bp["ftm"], "fta": bp["fta"],
                "tov": bp["tov"], "minutes": bp["minutes"],
                "ttfl_score": bp["ttfl_score"],
                "is_home": bp["is_home"],
            }
            for bp in box_players
        ]
        db.upsert_game_logs(client, rows)
        touched_player_ids.update(r["player_id"] for r in rows)
        dnps = sum(1 for r in rows if r["minutes"] == 0)
        print(f"  {g['date']} · {g['id']} · {len(rows)} rows ({dnps} DNP)")

    print(f"\nRecomputing aggregates for {len(touched_player_ids)} players…")
    for pid in touched_player_ids:
        logs = db.get_player_game_logs(client, pid, limit=40)
        if not logs:
            continue
        aggs = compute_player_aggregates(logs)
        aggs["updated_at"] = datetime.now(UTC).isoformat()
        client.table("players").update(aggs).eq("id", pid).execute()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    args = parser.parse_args()
    backfill(days=args.days)
