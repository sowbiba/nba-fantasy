"""One-shot: backfill series_id on matchup_aggregates rows that were
written with NULL because seed_playoffs hadn't tagged the playoff games
yet (e.g. round 2 before the gameLabel parser was fixed).

For each row with series_id IS NULL, look up the playoff games it
processed (game_id starting with '004'). If they all belong to the
same series — and that series is now linked in `games` — promote the
row's series_id. Mixed regular-season + playoff rows are left
untouched (the regular-season data is still valid as a season-wide
aggregate).

Safe to re-run: rows already migrated (series_id NOT NULL) are
skipped.

    python -m sync.migrate_matchup_series_id
"""
from sync.db import get_client


def migrate() -> None:
    sb = get_client()
    rows: list[dict] = []
    page = 0
    page_size = 1000
    while True:
        chunk = (
            sb.table("matchup_aggregates")
            .select("id, player_id, opponent_team, processed_game_ids")
            .is_("series_id", "null")
            .range(page * page_size, page * page_size + page_size - 1)
            .execute()
            .data
        ) or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1
    print(f"{len(rows)} aggregate rows with series_id NULL")

    # Build a map: game_id → series_id (for playoff games only)
    playoff_games = (
        sb.table("games")
        .select("id, series_id")
        .like("id", "004%")
        .not_.is_("series_id", "null")
        .execute()
        .data
    ) or []
    game_to_series = {g["id"]: g["series_id"] for g in playoff_games}
    print(f"{len(game_to_series)} playoff games linked to a series")

    promoted = mixed = empty = 0
    for r in rows:
        gids = r.get("processed_game_ids") or []
        playoff_gids = [g for g in gids if g in game_to_series]
        non_playoff = [g for g in gids if g not in game_to_series]

        if not playoff_gids:
            empty += 1
            continue
        if non_playoff:
            mixed += 1
            continue

        series_ids = {game_to_series[g] for g in playoff_gids}
        if len(series_ids) != 1:
            # Spans multiple series (impossible in practice but guard anyway).
            mixed += 1
            continue

        sid = series_ids.pop()
        sb.table("matchup_aggregates").update({"series_id": sid}).eq(
            "id", r["id"]
        ).execute()
        promoted += 1

    print(
        f"Migration done: {promoted} rows promoted, "
        f"{mixed} mixed (left as season aggregates), "
        f"{empty} purely regular-season."
    )


if __name__ == "__main__":
    migrate()
