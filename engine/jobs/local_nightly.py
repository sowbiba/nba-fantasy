"""Job local (PC, cron 23h50) : tout ce qui passe par stats.nba.com, dont les
IP GitHub sont bloquées.

- effectifs des 30 équipes (+ désactivation des joueurs coupés, seulement si
  les 30 effectifs ont répondu) ;
- calendrier des 35 prochains jours (stats.nba.com) ;
- historique de la saison via LeagueGameLog (1 appel pour toute la ligue),
  seule source de box scores (le CDN NBA, en 403 partout, n'est plus
  utilisé) ; les picks sont scorés (`score_picks`) juste après ce
  chargement, sans attendre le prochain `daily_sync` ;
- matchups bruts défenseur/joueur des matchs éligibles terminés.

`--backfill-season 2025-26` : charge une saison complète (SR + PO), une fois.
"""
import argparse
from datetime import UTC, date, datetime, timedelta

from engine.jobs.daily_sync import score_picks
from engine.rules.calendar import PARIS
from engine.rules.game_types import is_eligible, season_for_date

LOG_OVERLAP_DAYS = 3
MATCHUP_DAYS = 3
PLAYOFF_MONTHS = (4, 5, 6)
SCHEDULE_PAST_DAYS = 5
SCHEDULE_AHEAD_DAYS = 35


def to_raw_matchups(rows: list[dict], game: dict) -> list[dict]:
    raw = []
    for r in rows:
        off_team = r.get("off_team") or ""
        def_team = game["away_team"] if off_team == game["home_team"] else game["home_team"]
        raw.append({**r, "def_team": def_team, "series_id": game.get("series_id")})
    return raw


def _refresh_rosters(repo, nba, teams, season, warnings) -> None:
    before = {p["id"]: p for p in repo.load_players()}
    seen: set[int] = set()
    ok = 0
    for t in teams:
        try:
            rows = nba.roster(t["id"], t["abbreviation"], season)
        except Exception as exc:
            warnings.append(f"effectif {t['abbreviation']} : {type(exc).__name__}")
            continue
        if not rows:
            warnings.append(f"effectif {t['abbreviation']} : effectif vide")
            continue
        ok += 1
        repo.upsert_players(rows)
        seen |= {r["id"] for r in rows}
    if teams and ok == len(teams):
        repo.set_inactive(pid for pid, p in before.items() if p.get("active", True) and pid not in seen)


def _load_logs(repo, nba, season, season_type, date_from, warnings, drop_from: date | None = None) -> None:
    try:
        games, logs, players = nba.league_game_log(season, season_type, date_from)
    except Exception as exc:
        warnings.append(f"LeagueGameLog {season} {season_type} : {type(exc).__name__}")
        return
    if drop_from is not None:
        games = {gid: g for gid, g in games.items() if g["date"] < drop_from.isoformat()}
        logs = [l for l in logs if l["date"] < drop_from.isoformat() and l["game_id"] in games]
    if not logs:
        return
    known = {p["id"] for p in repo.load_players()}
    missing = [{"id": p["id"], "name": p["name"], "team": p["team"], "position": "F", "active": False}
               for pid, p in players.items() if pid not in known]
    if missing:
        repo.upsert_players(missing)
    repo.upsert_games(list(games.values()))
    repo.upsert_game_logs(logs)


def _load_schedule(repo, nba, season, today, warnings) -> None:
    try:
        rows = nba.schedule_stats(season, today - timedelta(days=SCHEDULE_PAST_DAYS),
                                  today + timedelta(days=SCHEDULE_AHEAD_DAYS))
    except Exception as exc:
        warnings.append(f"calendrier {season} : {type(exc).__name__}")
        return
    if rows:
        repo.upsert_games(rows)


def _load_matchups(repo, nba, today, warnings) -> None:
    finals = [g for g in repo.load_games_between(today - timedelta(days=MATCHUP_DAYS), today - timedelta(days=1))
              if is_eligible(g.get("game_type", "unknown")) and g.get("status") == "final"]
    done = repo.game_ids_with_matchups(g["id"] for g in finals)
    for g in finals:
        if g["id"] in done:
            continue
        try:
            rows = nba.matchups(g["id"])
        except Exception as exc:
            warnings.append(f"matchups {g['id']} : {type(exc).__name__}")
            continue
        if rows:
            repo.upsert_matchups_raw(to_raw_matchups(rows, g))


def run(repo, nba, today: date, teams: list[dict], backfill_season: str | None = None) -> list[str]:
    warnings: list[str] = []
    season = season_for_date(today)
    _refresh_rosters(repo, nba, teams, season, warnings)
    _load_schedule(repo, nba, season, today, warnings)
    if backfill_season:
        for season_type in ("Regular Season", "Playoffs"):
            _load_logs(repo, nba, backfill_season, season_type, None, warnings)
    else:
        start = today - timedelta(days=LOG_OVERLAP_DAYS)
        # Un match du jour peut encore être en direct : on ne l'ingère pas
        # comme "final" ici, le chevauchement de 3 jours le rattrapera la
        # nuit suivante une fois vraiment terminé.
        _load_logs(repo, nba, season, "Regular Season", start, warnings, drop_from=today)
        if today.month in PLAYOFF_MONTHS:
            _load_logs(repo, nba, season, "Playoffs", start, warnings, drop_from=today)
        score_picks(repo, season, today)
    _load_matchups(repo, nba, today, warnings)
    return warnings


def main() -> None:
    from nba_api.stats.static import teams as nba_teams

    from engine.io.guard import ApiGuard
    from engine.io.nba import NbaSource
    from engine.io.repo import SupabaseRepo

    parser = argparse.ArgumentParser(description="Job local (stats.nba.com)")
    parser.add_argument("--backfill-season", help="charge une saison complète, ex. 2025-26")
    args = parser.parse_args()

    guard = ApiGuard()
    repo = SupabaseRepo.from_env()
    today = datetime.now(UTC).astimezone(PARIS).date()
    log_id = repo.start_log("local_nightly")
    try:
        warnings = run(repo, NbaSource(guard, allow_stats=True), today, nba_teams.get_teams(),
                       backfill_season=args.backfill_season)
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    repo.finish_log(log_id, status="success", api_calls=guard.summary(),
                    error="; ".join(warnings) if warnings else None)
    print(f"local_nightly {today} : {len(warnings)} avertissement(s)")
    for w in warnings:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
