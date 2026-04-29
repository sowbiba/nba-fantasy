"""One-shot: walk recent finals and populate matchup_aggregates from
BoxScoreMatchupsV3. Run once after applying migration 009 so the
scoring layer has data to lean on.

    python -m sync.backfill_matchups --days 30
"""
import argparse
from datetime import date, timedelta

from sync import db
from sync.matchups import update_aggregates_for_game


def backfill(days: int = 30) -> None:
    client = db.get_client()
    today = date.today()
    start = today - timedelta(days=days)

    games = (
        client.table("games")
        .select("id, date, home_team, away_team, series_id")
        .gte("date", start.isoformat())
        .lte("date", today.isoformat())
        .eq("status", "final")
        .order("date")
        .execute()
        .data
    ) or []
    print(f"{len(games)} final games in [{start} → {today}]")

    total_touched = 0
    for g in games:
        touched = update_aggregates_for_game(
            client,
            game_id=g["id"],
            home_team=g["home_team"],
            away_team=g["away_team"],
            series_id=g.get("series_id"),
        )
        total_touched += touched
        print(f"  {g['date']} · {g['id']} · {touched} (player, opponent) rows")

    print(f"\nDone. {total_touched} aggregate rows touched.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    backfill(days=args.days)
