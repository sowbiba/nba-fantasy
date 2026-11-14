"""Job local (PC, cron 23h50 et 9h00) : tout ce qui passe par stats.nba.com, dont les
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

# Fenêtre rechargée à chaque run (un seul appel LeagueGameLog) : 3 semaines,
# pour reprendre les corrections de stats que la NBA publie après coup (avec
# 3 jours, 35 scores TTFL étaient faux de 1 ou 2 points mi-novembre 2026).
LOG_OVERLAP_DAYS = 21
PENDING_DAYS = 3   # matchs terminés encore sans stats : fenêtre de la relance du matin
MATCHUP_DAYS = 3
PLAYOFF_MONTHS = (4, 5, 6)
SCHEDULE_PAST_DAYS = 5
SCHEDULE_AHEAD_DAYS = 35
# 48 min x 5 joueurs = 240 ; les minutes arrondies par joueur font osciller
# la somme d'une équipe entre ~238 et ~242. En dessous, le box score est
# encore partiel (stats.nba.com a parfois des quarts-temps de retard à 9h).
MIN_TEAM_MINUTES = 235


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


def _incomplete_games(logs: list[dict]) -> set[str]:
    minutes: dict[str, dict[bool, int]] = {}
    for l in logs:
        team = minutes.setdefault(l["game_id"], {})
        team[l["is_home"]] = team.get(l["is_home"], 0) + (l.get("minutes") or 0)
    return {gid for gid, t in minutes.items()
            if len(t) < 2 or min(t.values()) < MIN_TEAM_MINUTES}


def _keep_schedule_orientation(games: dict[str, dict], logs: list[dict], known: dict[str, dict]) -> None:
    """Le calendrier en base (stats.nba.com, chargé à l'avance) fait foi pour
    domicile/extérieur : sur terrain neutre, le journal des matchs choisit un
    côté arbitraire, ce qui casserait l'appariement ESPN (date, domicile,
    extérieur). On réaligne le match, son score et le côté de chaque log."""
    flipped = set()
    for gid, g in games.items():
        k = known.get(gid)
        if k and (k.get("home_team"), k.get("away_team")) == (g["away_team"], g["home_team"]):
            g["home_team"], g["away_team"] = g["away_team"], g["home_team"]
            if "home_score" in g and "away_score" in g:
                g["home_score"], g["away_score"] = g["away_score"], g["home_score"]
            flipped.add(gid)
    for l in logs:
        if l["game_id"] in flipped:
            l["is_home"] = not l["is_home"]


def _load_logs(repo, nba, season, season_type, date_from, warnings, drop_from: date | None = None) -> None:
    try:
        games, logs, players = nba.league_game_log(season, season_type, date_from)
    except Exception as exc:
        warnings.append(f"LeagueGameLog {season} {season_type} : {type(exc).__name__}")
        return
    if drop_from is not None:
        games = {gid: g for gid, g in games.items() if g["date"] < drop_from.isoformat()}
        logs = [l for l in logs if l["date"] < drop_from.isoformat() and l["game_id"] in games]
        # Un box score partiel écrirait des stats et un pick faux : on l'écarte,
        # le chevauchement de LOG_OVERLAP_DAYS le reprendra au run suivant.
        for gid in sorted(_incomplete_games(logs)):
            warnings.append(f"box score incomplet {gid} : ignoré jusqu'au prochain run")
            games.pop(gid, None)
        logs = [l for l in logs if l["game_id"] in games]
    if not logs:
        return
    _keep_schedule_orientation(games, logs, {g["id"]: g for g in repo.load_games_of_seasons([season])})
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


def _load_recent_logs(repo, nba, season, today, warnings) -> None:
    start = today - timedelta(days=LOG_OVERLAP_DAYS)
    # Un match du jour peut encore être en direct : on ne l'ingère pas
    # comme "final" ici, le chevauchement de 3 jours le rattrapera la
    # nuit suivante une fois vraiment terminé.
    _load_logs(repo, nba, season, "Regular Season", start, warnings, drop_from=today)
    if today.month in PLAYOFF_MONTHS:
        _load_logs(repo, nba, season, "Playoffs", start, warnings, drop_from=today)
    score_picks(repo, season, today)


def pending_games(repo, today: date) -> list[str]:
    """Matchs éligibles terminés des derniers jours sans aucune stat en base
    (box score encore incomplet chez stats.nba.com au run précédent)."""
    finals = [g["id"] for g in repo.load_games_between(today - timedelta(days=PENDING_DAYS),
                                                       today - timedelta(days=1))
              if is_eligible(g.get("game_type", "unknown")) and g.get("status") == "final"]
    done = repo.game_ids_with_logs(finals)
    return sorted(gid for gid in finals if gid not in done)


def retry_incomplete(repo, nba, today: date) -> list[str] | None:
    """Relance du matin (cron 9h30→12h) : `None` si rien n'attend, sans aucun
    appel à stats.nba.com ; sinon recharge les stats et score les picks."""
    if not pending_games(repo, today):
        return None
    warnings: list[str] = []
    _load_recent_logs(repo, nba, season_for_date(today), today, warnings)
    return warnings


def run(repo, nba, today: date, teams: list[dict], backfill_season: str | None = None,
        matchups: bool = True) -> list[str]:
    warnings: list[str] = []
    season = season_for_date(today)
    _refresh_rosters(repo, nba, teams, season, warnings)
    _load_schedule(repo, nba, season, today, warnings)
    if backfill_season:
        for season_type in ("Regular Season", "Playoffs"):
            _load_logs(repo, nba, backfill_season, season_type, None, warnings)
    else:
        _load_recent_logs(repo, nba, season, today, warnings)
    if matchups:
        _load_matchups(repo, nba, today, warnings)
    return warnings


def main() -> None:
    from nba_api.stats.static import teams as nba_teams

    from engine.io.guard import ApiGuard
    from engine.io.nba import NbaSource
    from engine.io.repo import SupabaseRepo

    parser = argparse.ArgumentParser(description="Job local (stats.nba.com)")
    parser.add_argument("--backfill-season", help="charge une saison complète, ex. 2025-26")
    parser.add_argument("--no-matchups", dest="matchups", action="store_false",
                        help="runs du matin : stats.nba.com n'a pas encore les matchups de la nuit (IndexError "
                             "puis disjoncteur, ~3 min perdues) ; le run de 23h50 les charge")
    parser.add_argument("--retry-incomplete", action="store_true",
                        help="recharge seulement les stats des matchs terminés encore sans box score")
    args = parser.parse_args()

    guard = ApiGuard()
    repo = SupabaseRepo.from_env()
    today = datetime.now(UTC).astimezone(PARIS).date()
    if args.retry_incomplete:
        _main_retry(repo, NbaSource(guard, allow_stats=True), guard, today)
        return
    log_id = repo.start_log("local_nightly")
    try:
        warnings = run(repo, NbaSource(guard, allow_stats=True), today, nba_teams.get_teams(),
                       backfill_season=args.backfill_season, matchups=args.matchups)
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    repo.finish_log(log_id, status="success", api_calls=guard.summary(),
                    error="; ".join(warnings) if warnings else None)
    print(f"local_nightly {today} : {len(warnings)} avertissement(s)")
    for w in warnings:
        print(f"  ⚠ {w}")


def _main_retry(repo, nba, guard, today: date) -> None:
    pending = pending_games(repo, today)
    if not pending:
        print(f"local_nightly retry {today} : rien en attente")
        return
    log_id = repo.start_log("local_nightly_retry")
    try:
        warnings = retry_incomplete(repo, nba, today) or []
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    left = pending_games(repo, today)
    repo.finish_log(log_id, status="success", api_calls=guard.summary(),
                    error="; ".join(warnings) if warnings else None)
    print(f"local_nightly retry {today} : {len(pending) - len(left)}/{len(pending)} match(s) rattrapé(s)"
          + (f", encore en attente : {', '.join(left)}" if left else ""))


if __name__ == "__main__":
    main()
