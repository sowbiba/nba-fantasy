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

INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"


def fetch_team_injuries(team_tricode: str) -> list[dict]:
    """Fetch injuries for a single team.
    Returns list of dicts: {"name": str, "status": str, "detail": str}
    """
    espn_id = ESPN_TEAM_IDS.get(team_tricode)
    if espn_id is None:
        return []

    url = INJURY_URL.format(team_id=espn_id)
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    injuries = []
    for item in data.get("items", []):
        athlete = item.get("athlete", {})
        name = athlete.get("displayName", "")
        status = item.get("status", "")
        detail_type = item.get("type", {}).get("description", "")
        detail = item.get("details", {}).get("detail", detail_type)

        if name and status:
            injuries.append({
                "name": name,
                "status": status,
                "detail": detail,
            })

    return injuries


def fetch_all_injuries(teams: list[str] | None = None) -> dict[str, list[dict]]:
    """Fetch injuries for all teams (or a subset).
    Returns {team_tricode: [{"name", "status", "detail"}, ...]}
    """
    if teams is None:
        teams = list(ESPN_TEAM_IDS.keys())

    all_injuries = {}
    for tricode in teams:
        team_injuries = fetch_team_injuries(tricode)
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
