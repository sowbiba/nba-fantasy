"""Pull the full NBA league schedule and upsert upcoming games."""
from datetime import date, datetime

import httpx

from sync.db import get_client


NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"


def load(days_ahead: int = 30):
    client = get_client()
    resp = httpx.get(
        NBA_SCHEDULE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com"},
        timeout=15,
    )
    resp.raise_for_status()
    dates = resp.json().get("leagueSchedule", {}).get("gameDates", [])

    today = date.today()
    count = 0

    for gd in dates:
        raw = gd.get("gameDate", "")
        try:
            dt = datetime.strptime(raw[:10], "%m/%d/%Y").date()
        except ValueError:
            continue
        if dt < today or (dt - today).days > days_ahead:
            continue

        iso = dt.isoformat()
        for g in gd.get("games", []):
            gid = g.get("gameId")
            home = g.get("homeTeam", {}).get("teamTricode")
            away = g.get("awayTeam", {}).get("teamTricode")
            if not gid:
                continue
            # Accept "TBD" opponents — we'll filter them at planning time
            payload = {
                "id": gid,
                "date": iso,
                "home_team": home or "TBD",
                "away_team": away or "TBD",
                "tip_off": g.get("gameDateTimeUTC") or None,
                "status": "scheduled",
            }
            client.table("games").upsert(payload, on_conflict="id").execute()
            count += 1

    print(f"Upserted {count} games in the next {days_ahead} days.")


if __name__ == "__main__":
    load(days_ahead=30)
