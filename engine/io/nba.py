"""Sources NBA : cdn.nba.com (calendrier, scoreboard, box scores live) et
stats.nba.com (effectifs, historique LeagueGameLog, matchups), réservé au
cron local car les IP GitHub y sont bloquées.

Les parseurs sont purs et testés ; NbaSource ajoute l'accès réseau derrière
ApiGuard.
"""
from datetime import date, datetime

import httpx
from nba_api.live.nba.endpoints import BoxScore, ScoreBoard
from nba_api.live.nba.library import http as _live_http
from nba_api.stats.endpoints import BoxScoreMatchupsV3, CommonTeamRoster, LeagueGameLog
from nba_api.stats.library import http as _stats_http

from engine.io.guard import ApiGuard
from engine.rules.scoring import compute_ttfl_score

SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}

# Akamai refuse les requêtes sans Referer www.nba.com (403) : on l'ajoute aux
# en-têtes de nba_api (live et stats).
_live_http.NBALiveHTTP.headers = {**_live_http.NBALiveHTTP.headers, "Referer": "https://www.nba.com/"}
_stats_http.NBAStatsHTTP.headers = {**_stats_http.NBAStatsHTTP.headers, "Referer": "https://www.nba.com/"}


# --- parseurs purs -------------------------------------------------------

def parse_schedule(payload: dict, start: date, end: date) -> list[dict]:
    rows = []
    for gd in payload.get("leagueSchedule", {}).get("gameDates", []):
        try:
            d = datetime.strptime(gd.get("gameDate", "")[:10], "%m/%d/%Y").date()
        except ValueError:
            continue
        if d < start or d > end:
            continue
        for g in gd.get("games", []):
            if not g.get("gameId"):
                continue
            rows.append({
                "id": g["gameId"],
                "date": d.isoformat(),
                "home_team": (g.get("homeTeam") or {}).get("teamTricode") or "TBD",
                "away_team": (g.get("awayTeam") or {}).get("teamTricode") or "TBD",
                "tip_off": g.get("gameDateTimeUTC") or None,
            })
    return rows


def parse_scoreboard(scoreboard: dict, today: date) -> list[dict]:
    """Le scoreboard live garde parfois la journée NBA précédente active le
    matin (heure de Paris) : on se fie à son propre gameDate."""
    sb_date = today
    if scoreboard.get("gameDate"):
        try:
            sb_date = datetime.strptime(scoreboard["gameDate"], "%Y-%m-%d").date()
        except ValueError:
            sb_date = today
    status_by_code = {3: "final", 2: "live"}
    rows = []
    for g in scoreboard.get("games", []):
        status = status_by_code.get(g.get("gameStatus"), "scheduled")
        played = status != "scheduled"
        rows.append({
            "id": g["gameId"],
            "date": sb_date.isoformat(),
            "home_team": g["homeTeam"]["teamTricode"],
            "away_team": g["awayTeam"]["teamTricode"],
            "tip_off": g.get("gameTimeUTC"),
            "status": status,
            "home_score": (g["homeTeam"].get("score") or 0) if played else None,
            "away_score": (g["awayTeam"].get("score") or 0) if played else None,
        })
    return rows


def _iso_minutes(value: str | None) -> int:
    if not value or "M" not in value:
        return 0
    try:
        return int(value.split("T")[1].split("M")[0])
    except (IndexError, ValueError):
        return 0


def _stat_line(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov) -> dict:
    return {
        "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
        "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta, "tov": tov,
        "ttfl_score": compute_ttfl_score(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov),
    }


def parse_live_box_score(game: dict, game_date: str) -> list[dict]:
    """Lignes game_logs d'un box score CDN. `game_date` = date US du match
    (games.date) : la date UTC du CDN décale les matchs tardifs d'un jour.
    Les DNP (0 minute) sont gardés : ils alimentent P(joue)."""
    rows = []
    for side, is_home in (("homeTeam", True), ("awayTeam", False)):
        team = game[side]
        for p in team.get("players", []):
            s = p.get("statistics") or {}
            rows.append({
                "player_id": int(p["personId"]),
                "game_id": game["gameId"],
                "date": game_date,
                "team": team["teamTricode"],
                "minutes": _iso_minutes(s.get("minutes")),
                "fouls": s.get("foulsPersonal", 0) or 0,
                "is_home": is_home,
                **_stat_line(
                    s.get("points", 0) or 0, s.get("reboundsTotal", 0) or 0, s.get("assists", 0) or 0,
                    s.get("steals", 0) or 0, s.get("blocks", 0) or 0,
                    s.get("fieldGoalsMade", 0) or 0, s.get("fieldGoalsAttempted", 0) or 0,
                    s.get("threePointersMade", 0) or 0, s.get("threePointersAttempted", 0) or 0,
                    s.get("freeThrowsMade", 0) or 0, s.get("freeThrowsAttempted", 0) or 0,
                    s.get("turnovers", 0) or 0,
                ),
            })
    return rows


def _parse_date(value: str) -> str:
    """LeagueGameLog renvoie « 2025-10-22 » ; PlayerGameLog « OCT 22, 2025 »."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date de match illisible : {value!r}")


def _minutes(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    if ":" in text:
        return int(text.split(":")[0] or 0)
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_league_game_log(rows: list[dict]) -> tuple[dict[str, dict], list[dict], dict[int, dict]]:
    games: dict[str, dict] = {}
    logs: list[dict] = []
    players: dict[int, dict] = {}
    for r in rows:
        team = r["TEAM_ABBREVIATION"]
        matchup = r.get("MATCHUP", "")
        if " vs. " in matchup:
            is_home, other = True, matchup.split(" vs. ")[1].strip()
        else:
            is_home, other = False, matchup.split(" @ ")[-1].strip()
        game_date = _parse_date(str(r["GAME_DATE"]))
        gid = str(r["GAME_ID"])
        games[gid] = {"id": gid, "date": game_date,
                      "home_team": team if is_home else other,
                      "away_team": other if is_home else team, "status": "final"}
        logs.append({
            "player_id": int(r["PLAYER_ID"]), "game_id": gid, "date": game_date, "team": team,
            "minutes": _minutes(r.get("MIN")), "fouls": int(r.get("PF") or 0), "is_home": is_home,
            **_stat_line(int(r["PTS"] or 0), int(r["REB"] or 0), int(r["AST"] or 0), int(r["STL"] or 0),
                         int(r["BLK"] or 0), int(r["FGM"] or 0), int(r["FGA"] or 0), int(r["FG3M"] or 0),
                         int(r["FG3A"] or 0), int(r["FTM"] or 0), int(r["FTA"] or 0), int(r["TOV"] or 0)),
        })
        players[int(r["PLAYER_ID"])] = {"id": int(r["PLAYER_ID"]), "name": r["PLAYER_NAME"], "team": team}
    return games, logs, players


def _short_position(position: str) -> str:
    if "Guard" in position or position in ("G", "G-F"):
        return "G"
    if "Forward" in position or position in ("F", "F-G", "F-C"):
        return "F"
    if "Center" in position or position == "C":
        return "C"
    return "F"


def parse_roster(rows: list[dict], tricode: str) -> list[dict]:
    return [{"id": int(r["PLAYER_ID"]), "name": r["PLAYER"], "team": tricode,
             "position": _short_position(r.get("POSITION") or ""), "active": True} for r in rows]


def parse_matchups(records: list[dict], game_id: str) -> list[dict]:
    return [{
        "game_id": str(r.get("gameId") or game_id),
        "off_team": r.get("teamTricode") or "",
        "off_player_id": int(r["personIdOff"]),
        "off_player_name": f"{r['firstNameOff']} {r['familyNameOff']}",
        "def_player_id": int(r["personIdDef"]),
        "def_player_name": f"{r['firstNameDef']} {r['familyNameDef']}",
        "matchup_seconds": float(r.get("matchupMinutesSort") or 0),
        "partial_possessions": float(r.get("partialPossessions") or 0),
        "player_points": int(r.get("playerPoints") or 0),
        "matchup_assists": int(r.get("matchupAssists") or 0),
        "matchup_turnovers": int(r.get("matchupTurnovers") or 0),
        "matchup_blocks": int(r.get("matchupBlocks") or 0),
        "matchup_fgm": int(r.get("matchupFieldGoalsMade") or 0),
        "matchup_fga": int(r.get("matchupFieldGoalsAttempted") or 0),
        "matchup_tpm": int(r.get("matchupThreePointersMade") or 0),
        "matchup_tpa": int(r.get("matchupThreePointersAttempted") or 0),
        "matchup_ftm": int(r.get("matchupFreeThrowsMade") or 0),
        "matchup_fta": int(r.get("matchupFreeThrowsAttempted") or 0),
    } for r in records]


# --- accès réseau --------------------------------------------------------

class NbaSource:
    def __init__(self, guard: ApiGuard, *, allow_stats: bool = False):
        self.guard = guard
        self.allow_stats = allow_stats

    def _require_stats(self) -> None:
        if not self.allow_stats:
            raise RuntimeError("stats.nba.com réservé au cron local (IP GitHub bloquées)")

    def schedule(self, start: date, end: date) -> list[dict]:
        def fetch():
            resp = httpx.get(SCHEDULE_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        return parse_schedule(self.guard.call("cdn.nba.com", fetch), start, end)

    def scoreboard(self, today: date) -> list[dict]:
        board = self.guard.call("cdn.nba.com", lambda: ScoreBoard().get_dict()["scoreboard"])
        return parse_scoreboard(board, today)

    def box_score(self, game_id: str, game_date: str) -> list[dict]:
        """[] si le CDN a purgé le box score : le cron local le rattrapera via
        LeagueGameLog."""
        try:
            game = self.guard.call("cdn.nba.com", lambda: BoxScore(game_id=game_id).get_dict()["game"])
        except Exception:
            return []
        return parse_live_box_score(game, game_date)

    def league_game_log(self, season: str, season_type: str, date_from: date | None = None):
        self._require_stats()
        kwargs = {"season": season, "season_type_all_star": season_type,
                  "player_or_team_abbreviation": "P", "timeout": 60}
        if date_from is not None:
            kwargs["date_from_nullable"] = date_from.strftime("%m/%d/%Y")
        rows = self.guard.call(
            "stats.nba.com", lambda: LeagueGameLog(**kwargs).get_normalized_dict()["LeagueGameLog"])
        return parse_league_game_log(rows)

    def roster(self, team_id: int, tricode: str) -> list[dict]:
        self._require_stats()
        rows = self.guard.call(
            "stats.nba.com",
            lambda: CommonTeamRoster(team_id=str(team_id), timeout=12).get_normalized_dict()["CommonTeamRoster"],
            is_empty=lambda r: not r,
        )
        return parse_roster(rows, tricode)

    def matchups(self, game_id: str) -> list[dict]:
        self._require_stats()
        records = self.guard.call(
            "stats.nba.com",
            lambda: BoxScoreMatchupsV3(game_id=game_id, timeout=30).player_stats.get_data_frame().to_dict("records"),
            is_empty=lambda r: not r,
        )
        return parse_matchups(records, game_id)
