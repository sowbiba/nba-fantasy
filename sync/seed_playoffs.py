"""Seed the `series` table from the NBA playoff schedule + backfill
`games.series_id` and `games.game_number` for playoff games.

Pulls data from cdn.nba.com/static/json/staticData/scheduleLeagueV2.json
and parses any game with gameLabel containing "First Round", "Conference
Semifinals", "Conference Finals", or "NBA Finals".

For each unique (home_team, away_team) pair in a round, creates one
`series` row. Then updates all games from that series to link back.

Re-runnable: uses upsert on series and update on games.
"""
import re
from datetime import datetime

import httpx

from sync.db import get_client


NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

# Map NBA "gameLabel" → internal round number
ROUND_LABELS = {
    "East First Round": 1,
    "West First Round": 1,
    "East Conf Semifinals": 2,
    "West Conf Semifinals": 2,
    "East Conf Finals": 3,
    "West Conf Finals": 3,
    "NBA Finals": 4,
}


def fetch_schedule() -> list[dict]:
    resp = httpx.get(
        NBA_SCHEDULE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("leagueSchedule", {}).get("gameDates", [])


def series_key(team_a: str, team_b: str) -> tuple[str, str]:
    """Normalized unordered key for a series (so NYK-ATL == ATL-NYK)."""
    return tuple(sorted((team_a, team_b)))


def parse_series_text(text: str) -> tuple[int, int, str | None]:
    """Parse NBA seriesText into (leader_wins, trailer_wins, leader_team).

    Examples:
      "Series tied 0-0"     -> (0, 0, None)
      "Series tied 2-2"     -> (2, 2, None)
      "NYK leads 1-0"       -> (1, 0, "NYK")
      "ATL wins 4-1"        -> (4, 1, "ATL")  # series ended
      "ATL won series 4-2"  -> (4, 2, "ATL")  # series ended
      "ATL advances 4-0"    -> (4, 0, "ATL")  # series ended
      "ATL clinch 7 seed"   -> (0, 0, None)   # play-in, handled separately
    """
    if not text:
        return (0, 0, None)
    m = re.match(r"Series tied (\d)-(\d)", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), None)
    m = re.match(r"(\w{2,4}) leads (\d)-(\d)", text)
    if m:
        return (int(m.group(2)), int(m.group(3)), m.group(1))
    # After a series ends, NBA's seriesText switches from "leads" to a
    # closing variant. Without this branch the series stays at the last
    # "leads 3-X" snapshot and is never marked completed, so phantom G6/G7
    # keep feeding tonight's recos.
    m = re.match(
        r"(\w{2,4})\s+(?:wins?|won|advances?|sweeps?|clinch(?:es)?)"
        r"(?:\s+series)?\s+(\d)-(\d)",
        text,
    )
    if m:
        return (int(m.group(2)), int(m.group(3)), m.group(1))
    return (0, 0, None)


def seed():
    client = get_client()
    dates = fetch_schedule()

    # Collect all playoff games per series
    series_map: dict[tuple[str, str], dict] = {}
    playoff_games: list[dict] = []

    for gd in dates:
        raw = gd.get("gameDate", "")
        try:
            dt = datetime.strptime(raw[:10], "%m/%d/%Y").date()
            iso = dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

        for g in gd.get("games", []):
            label = g.get("gameLabel", "")
            round_num = ROUND_LABELS.get(label)
            if round_num is None:
                continue

            home = g.get("homeTeam", {}).get("teamTricode")
            away = g.get("awayTeam", {}).get("teamTricode")
            if not home or not away or home == "TBD" or away == "TBD":
                continue

            key = series_key(home, away)
            if key not in series_map:
                series_map[key] = {
                    "round": round_num,
                    "home_team": home,
                    "away_team": away,
                    "home_wins": 0,
                    "away_wins": 0,
                    "status": "active",
                }

            game_num_str = g.get("seriesGameNumber", "") or ""
            m = re.search(r"(\d+)", game_num_str)
            game_num = int(m.group(1)) if m else None

            # Game 1 determines home-court advantage
            if game_num == 1:
                series_map[key]["home_team"] = home
                series_map[key]["away_team"] = away

            # Update wins from seriesText (latest non-zero wins = most recent info)
            leader_wins, trailer_wins, leader_team = parse_series_text(
                g.get("seriesText", "")
            )
            if leader_wins > 0 or trailer_wins > 0:
                series_home = series_map[key]["home_team"]
                if leader_team == series_home:
                    hw, aw = leader_wins, trailer_wins
                elif leader_team is not None:
                    hw, aw = trailer_wins, leader_wins
                else:  # tied
                    hw, aw = leader_wins, trailer_wins
                # Keep the latest/highest win counts we've seen
                if hw + aw > series_map[key]["home_wins"] + series_map[key]["away_wins"]:
                    series_map[key]["home_wins"] = hw
                    series_map[key]["away_wins"] = aw
                # Mark completed if someone reached 4
                if hw == 4 or aw == 4:
                    series_map[key]["status"] = "completed"

            playoff_games.append({
                "game_id": g.get("gameId"),
                "date": iso,
                "home": home,
                "away": away,
                "game_number": game_num,
                "series_key": key,
            })

    if not series_map:
        print("No playoff series found in schedule.")
        return

    print(f"Found {len(series_map)} playoff series in schedule.")

    # Load existing series to match by (round, home_team, away_team)
    existing = client.table("series").select("*").execute().data
    existing_by_key = {}
    for row in existing:
        k = (row["round"], series_key(row["home_team"], row["away_team"]))
        existing_by_key[k] = row

    key_to_id: dict[tuple[str, str], int] = {}
    inserted_count = 0
    updated_count = 0
    preserved_count = 0
    for s in series_map.values():
        unordered = series_key(s["home_team"], s["away_team"])
        lookup_key = (s["round"], unordered)
        existing_row = existing_by_key.get(lookup_key)

        payload = {
            "round": s["round"],
            "home_team": s["home_team"],
            "away_team": s["away_team"],
            "home_wins": s["home_wins"],
            "away_wins": s["away_wins"],
            "status": s["status"],
        }

        if existing_row:
            # NBA's static schedule lags reality (a Game 4 win that closes a
            # sweep can take ~24h to appear in seriesText). Never let stale
            # NBA data overwrite a completed series or downgrade higher win
            # counts already recorded locally.
            existing_total = (
                (existing_row.get("home_wins") or 0)
                + (existing_row.get("away_wins") or 0)
            )
            incoming_total = s["home_wins"] + s["away_wins"]
            if existing_row.get("status") == "completed" or incoming_total < existing_total:
                key_to_id[unordered] = existing_row["id"]
                preserved_count += 1
                continue

            client.table("series").update(payload).eq(
                "id", existing_row["id"]
            ).execute()
            key_to_id[unordered] = existing_row["id"]
            updated_count += 1
        else:
            result = client.table("series").insert(payload).execute()
            new_id = result.data[0]["id"]
            key_to_id[unordered] = new_id
            inserted_count += 1

    print(
        f"Series: {inserted_count} inserted, {updated_count} updated, "
        f"{preserved_count} preserved (completed or stale)."
    )

    # Now update games with series_id and game_number
    updated_games = 0
    for pg in playoff_games:
        sid = key_to_id.get(pg["series_key"])
        if sid is None or not pg["game_id"]:
            continue
        payload = {"series_id": sid}
        if pg["game_number"] is not None:
            payload["game_number"] = pg["game_number"]
        client.table("games").update(payload).eq("id", pg["game_id"]).execute()
        updated_games += 1

    print(f"Linked {updated_games} games to their series.")

    # Authoritative reconciliation: recompute each series' wins/status from
    # the actual final-game results. NBA's `seriesText` lags reality — by
    # several hours after a clincher, sometimes longer if the closing-
    # variant string isn't in our regex. Final game scores are ground truth.
    reconciled = 0
    for unordered, sid in key_to_id.items():
        # Pull all final games linked to this series.
        finals = (
            client.table("games")
            .select("home_team,away_team,home_score,away_score,status")
            .eq("series_id", sid)
            .eq("status", "final")
            .execute()
            .data
        ) or []
        if not finals:
            continue

        series_row = (
            client.table("series").select("*").eq("id", sid).execute().data
        )
        if not series_row:
            continue
        s = series_row[0]
        home_team = s["home_team"]

        hw = aw = 0
        for fg in finals:
            hs, as_ = fg.get("home_score"), fg.get("away_score")
            if hs is None or as_ is None:
                continue
            winner = fg["home_team"] if hs > as_ else fg["away_team"]
            if winner == home_team:
                hw += 1
            else:
                aw += 1

        new_status = "completed" if hw == 4 or aw == 4 else "active"
        if (
            hw != (s.get("home_wins") or 0)
            or aw != (s.get("away_wins") or 0)
            or new_status != s.get("status")
        ):
            client.table("series").update(
                {"home_wins": hw, "away_wins": aw, "status": new_status}
            ).eq("id", sid).execute()
            reconciled += 1

    if reconciled:
        print(f"Reconciled {reconciled} series from final-game results.")

    # Summary — read from DB (not series_map) so completed/stale-protected
    # rows show their authoritative wins, not NBA's lagging snapshot.
    print()
    final = client.table("series").select("*").order("round").execute().data
    for s in final:
        flag = " ✅" if s["status"] == "completed" else ""
        print(
            f"  R{s['round']} · {s['home_team']} (home court) vs {s['away_team']}"
            f" ({s['home_wins']}-{s['away_wins']}){flag}"
        )


if __name__ == "__main__":
    seed()
