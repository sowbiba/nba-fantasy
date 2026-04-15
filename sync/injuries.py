# sync/injuries.py
"""Fetch player injury statuses from ESPN unofficial API."""
import httpx

ESPN_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4,
    "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GSW": 9,
    "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MEM": 29,
    "MIA": 14, "MIL": 15, "MIN": 16, "NOP": 3, "NYK": 18,
    "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22,
    "SAC": 23, "SAS": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}

GLOBAL_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

# Reverse mapping: ESPN team displayName -> tricode
ESPN_NAME_TO_TRICODE = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}

# Also map ESPN team ID to tricode
ESPN_ID_TO_TRICODE = {str(v): k for k, v in ESPN_TEAM_IDS.items()}


def fetch_all_injuries(teams: list[str] | None = None) -> dict[str, list[dict]]:
    """Fetch injuries for all teams from ESPN global endpoint.

    Returns {team_tricode: [{"name", "status", "detail"}, ...]}
    """
    try:
        resp = httpx.get(GLOBAL_INJURIES_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {}

    all_injuries: dict[str, list[dict]] = {}

    for team_data in data.get("injuries", []):
        team_name = team_data.get("displayName", "")
        team_id = team_data.get("id", "")
        tricode = ESPN_NAME_TO_TRICODE.get(team_name) or ESPN_ID_TO_TRICODE.get(team_id)
        if not tricode:
            continue
        if teams is not None and tricode not in teams:
            continue

        team_injuries = []
        for inj in team_data.get("injuries", []):
            athlete = inj.get("athlete", {})
            name = athlete.get("displayName", "")
            status = inj.get("status", "")
            if isinstance(status, dict):
                status = status.get("type", status.get("name", ""))

            # `details` contains the real injury info: type (body part), side, returnDate
            details = inj.get("details") if isinstance(inj.get("details"), dict) else {}
            body_part = details.get("type", "") if details else ""
            location = details.get("location", "") if details else ""
            side = details.get("side", "") if details else ""

            # Build a human-readable detail string e.g. "Achilles (Right Leg)"
            detail_parts = []
            if body_part and body_part != "Not Specified":
                detail_parts.append(body_part)
            if side and location and location != "Not Specified":
                detail_parts.append(f"({side} {location})".strip())
            elif location and location != "Not Specified":
                detail_parts.append(f"({location})")
            detail = " ".join(detail_parts).strip()

            return_date = details.get("returnDate") if details else None
            short_comment = inj.get("shortComment", "")
            updated_at = inj.get("date", "")

            if name and status:
                team_injuries.append({
                    "name": name,
                    "status": status,
                    "detail": detail,
                    "return_date": return_date,
                    "short_comment": short_comment,
                    "updated_at": updated_at,
                })

        if team_injuries:
            all_injuries[tricode] = team_injuries

    return all_injuries


def match_injury_to_player(
    injury_name: str, players: list[dict]
) -> int | None:
    """Match an ESPN injury name to a player dict by fuzzy name matching.
    Players should have 'name' and 'id' keys.
    Returns player_id or None.
    """
    injury_lower = injury_name.lower().strip()
    for p in players:
        player_lower = p["name"].lower().strip()
        if player_lower == injury_lower:
            return p["id"]
        injury_last = injury_lower.split()[-1] if injury_lower else ""
        player_last = player_lower.split()[-1] if player_lower else ""
        if injury_last and injury_last == player_last:
            if len(injury_lower.split()) >= 2 and len(player_lower.split()) >= 2:
                if injury_lower.split()[0][0] == player_lower.split()[0][0]:
                    return p["id"]
            elif injury_last == player_last:
                return p["id"]
    return None
