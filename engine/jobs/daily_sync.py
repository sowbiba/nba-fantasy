"""Job quotidien (GitHub Actions, plusieurs fois/jour) : statuts et scores
ESPN, scoring des picks, blessures, soirées, recommandations du soir et
plan 30 jours.

Jamais d'appel à stats.nba.com (IP GitHub bloquées) ni au CDN NBA (403
partout). Calendrier et box scores viennent de `local_nightly` (stats.nba.com,
depuis le PC local). Chaque étape réseau peut échouer sans faire tomber le
job : la décision tourne alors sur les données en base, et l'échec est noté
dans `warnings`.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from engine.explain.texts import plan_explanation, reco_texts, tier
from engine.io.espn import match_injury_to_player
from engine.rules.availability import PickRow, SecondChance, SeriesRow
from engine.rules.calendar import PARIS, build_nights
from engine.rules.game_types import previous_season, season_for_date
from engine.stats.aggregates import player_aggregates
from engine.stats.profile import GameLog, build_profile, prior_minutes, role_scales
from engine.stats.team_defense import defense_factors
from engine.strategy.regular import HORIZON_DAYS, DecisionInputs, decide

SCHEDULE_PAST_DAYS = 5
SCHEDULE_AHEAD_DAYS = 35
PLAN_RETENTION = timedelta(days=7)
IDENTITY = ("id", "name", "team", "position")


@dataclass
class RunResult:
    players_updated: int = 0
    recommendations: int = 0
    plan_nights: int = 0
    warnings: list[str] = field(default_factory=list)


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _step(name: str, fn, result: RunResult):
    try:
        return fn()
    except Exception as exc:  # réseau, disjoncteur, budget : on continue
        result.warnings.append(f"{name} : {type(exc).__name__} {exc}")
        return None


def _is_settled(game: dict, today: date) -> bool:
    """Un match est "réglé" si son statut est final, ou si sa date remonte à
    au moins 2 jours : même si le statut n'a jamais été mis à jour côté NBA,
    un match d'il y a 2 jours ou plus est nécessairement terminé."""
    return game.get("status") == "final" or _d(game["date"]) <= today - timedelta(days=2)


def apply_scoreboard(repo, rows: list[dict], window_games: list[dict]) -> int:
    """Statuts/scores ESPN → table games, appariés par (date, domicile, extérieur)."""
    by_key = {(str(g["date"])[:10], g["home_team"], g["away_team"]): g for g in window_games}
    updates = []
    for r in rows:
        g = by_key.get((r["date"], r["home_team"], r["away_team"]))
        if g is None:
            continue
        updates.append({"id": g["id"], "date": g["date"], "home_team": g["home_team"], "away_team": g["away_team"],
                        "status": r["status"], "home_score": r["home_score"], "away_score": r["away_score"],
                        **({"tip_off": r["tip_off"]} if r.get("tip_off") else {})})
    if updates:
        repo.upsert_games(updates)
    return len(updates)


def score_picks(repo, season: str, today: date) -> None:
    # Toute la saison, pas seulement les 40 derniers jours : une correction
    # (`correct_pick`) peut porter sur une soirée plus ancienne et doit être
    # rescorée par la synchro suivante (spec §3.1).
    games = {g["id"]: g for g in repo.load_games_of_seasons([season])}
    picks = [p for p in repo.load_picks(season) if p.get("actual_score") is None and _d(p["date"]) < today]
    logs = {(l["player_id"], l["game_id"]): l for l in repo.load_game_logs([season])}
    with_logs = {gid for (_, gid) in logs}
    for p in picks:
        game = games.get(p["game_id"])
        if game is None or not _is_settled(game, today):
            continue
        log = logs.get((p["player_id"], p["game_id"]))
        if log is not None:
            repo.set_pick_score(p["id"], int(log["ttfl_score"]))
        elif p["game_id"] in with_logs:
            repo.set_pick_score(p["id"], 0)   # R7 : ne pas avoir joué = 0


def _apply_injuries(repo, injuries: dict[str, list[dict]]) -> None:
    players = repo.load_players()
    by_team: dict[str, list[dict]] = defaultdict(list)
    for p in players:
        by_team[p["team"]].append(p)
    injured: dict[int, dict] = {}
    for team, entries in injuries.items():
        for inj in entries:
            pid = match_injury_to_player(inj["name"], by_team.get(team, []))
            if pid is not None:
                injured[pid] = inj
    rows = []
    for p in players:
        inj = injured.get(p["id"])
        if inj is not None:
            rows.append({**{k: p[k] for k in IDENTITY}, "injury_status": inj["status"],
                         "injury_detail": inj.get("detail"), "injury_short_comment": inj.get("short_comment"),
                         "injury_return_date": inj.get("return_date"), "injury_updated_at": inj.get("updated_at")})
        elif p.get("injury_status"):
            rows.append({**{k: p[k] for k in IDENTITY}, "injury_status": None, "injury_detail": None,
                         "injury_short_comment": None, "injury_return_date": None})
    if rows:
        repo.upsert_players(rows)


def run(repo, fetch_scoreboard, fetch_injuries, today: date, now: datetime) -> RunResult:
    result = RunResult()
    season = season_for_date(today)
    prior = previous_season(season)

    window_games = repo.load_games_between(today - timedelta(days=1), today)
    for d in (today - timedelta(days=1), today):
        board = _step(f"scoreboard {d}", lambda d=d: fetch_scoreboard(d), result)
        if board:
            apply_scoreboard(repo, board, window_games)
    score_picks(repo, season, today)

    injuries = _step("blessures", fetch_injuries, result)
    if injuries:
        _apply_injuries(repo, injuries)

    players = {p["id"]: p for p in repo.load_players()}
    season_games = {g["id"]: g for g in repo.load_games_of_seasons([season, prior])}
    all_logs = [GameLog.from_row(r) for r in repo.load_game_logs([season, prior])]
    current_by_player: dict[int, list[GameLog]] = defaultdict(list)
    prior_by_player: dict[int, list[GameLog]] = defaultdict(list)
    for log in all_logs:
        (current_by_player if log.season == season else prior_by_player)[log.player_id].append(log)

    rosters: dict[str, list[int]] = defaultdict(list)
    for pid, p in players.items():
        if p.get("active", True):
            rosters[p["team"]].append(pid)
    scales = role_scales(prior_minutes([l for l in all_logs if l.season == prior]), rosters)
    profiles = {pid: build_profile(pid, current_by_player[pid], prior_by_player[pid], scales.get(p["team"], 1.0))
                for pid, p in players.items() if p.get("active", True)}
    defense = defense_factors([l for l in all_logs if l.season == season], [l for l in all_logs if l.season == prior],
                              season_games, {pid: p.get("position", "F") for pid, p in players.items()})

    aggregate_rows = [{**{k: p[k] for k in IDENTITY}, **player_aggregates(current_by_player[pid])}
                      for pid, p in players.items() if current_by_player[pid]]
    if aggregate_rows:
        repo.upsert_players(aggregate_rows)
    result.players_updated = len(aggregate_rows)

    window = repo.load_games_between(today - timedelta(days=SCHEDULE_PAST_DAYS), today + timedelta(days=SCHEDULE_AHEAD_DAYS))
    series_rows = repo.load_series(season)
    nights = [n for n in build_nights([g for g in window if _d(g["date"]) >= today], series_rows)]
    repo.replace_nights(today, [{"date": n.date.isoformat(), "season": n.season, "mode": n.mode,
                                 "n_eligible_games": n.n_eligible_games, "closing_at": n.closing_at.isoformat(),
                                 "is_phantom": n.is_phantom, "updated_at": now.isoformat()} for n in nights])

    recent_logs = {pid: [{"minutes": l.minutes} for l in sorted(logs, key=lambda l: l.date, reverse=True)[:5]]
                   for pid, logs in current_by_player.items()}
    picks = [PickRow(p["id"], p["player_id"], _d(p["date"]), p["mode"], p["season"]) for p in repo.load_picks(season)]
    second_chances = [SecondChance(s["pick_id"], s["player_id"], _d(s["bought_on"]), _d(s["expires_on"]))
                      for s in repo.load_second_chances()]
    series = [SeriesRow(s["season"], s["round"], s["home_team"], s["away_team"],
                        s.get("home_wins") or 0, s.get("away_wins") or 0, s["status"]) for s in series_rows]
    decision = decide(DecisionInputs(today=today, nights=nights, games=window, players=players,
                                     profiles=profiles, recent_logs=recent_logs, defense=defense,
                                     picks=picks, second_chances=second_chances, series=series))

    if decision.tonight is not None:
        rows = []
        for rank, rec in enumerate(decision.recommendations, start=1):
            pros, cons, verdict, tags = reco_texts(rec, rank, players[rec.cell.player_id]["name"])
            rows.append({
                "date": today.isoformat(), "player_id": rec.cell.player_id, "rank": rank,
                "estimated_score": round(rec.cell.p_play * rec.cell.projection, 1),
                "perf_score": round(rec.cell.projection, 1), "matchup_score": round(rec.cell.ctx.opp_factor, 3),
                "strategy_score": round(rec.cell.value, 1),
                "projection": round(rec.cell.projection, 1), "p_play": round(rec.cell.p_play, 3),
                "value": round(rec.cell.value, 1), "lock_value": round(rec.lock_value, 1),
                "locked_until": rec.locked_until.isoformat(),
                "best_future": None if rec.best_future is None else plan_explanation(rec.best_future),
                "pros": pros, "cons": cons, "verdict": verdict, "tier": tier(rank), "tags": tags,
                "computed_at": now.isoformat(),
            })
        repo.replace_recommendations(today, rows)
        result.recommendations = len(rows)

    plan_rows = [{"generated_at": now.isoformat(), "night": night.isoformat(), "player_id": c.player_id,
                  "is_x2": False, "projection": round(c.projection, 1), "p_play": round(c.p_play, 3),
                  "value": round(c.value, 1), "explanation": plan_explanation(c)}
                 for night, c in decision.plan.items() if (night - today).days < HORIZON_DAYS]
    repo.write_plan(plan_rows, keep_since=now - PLAN_RETENTION)
    result.plan_nights = len(plan_rows)
    return result


def main() -> None:
    from engine.io.espn import fetch_all_injuries, fetch_espn_scoreboard
    from engine.io.guard import ApiGuard
    from engine.io.repo import SupabaseRepo

    guard = ApiGuard()
    repo = SupabaseRepo.from_env()
    now = datetime.now(UTC)
    today = now.astimezone(PARIS).date()
    log_id = repo.start_log("daily_sync")
    try:
        result = run(repo, lambda d: fetch_espn_scoreboard(d, guard), lambda: fetch_all_injuries(guard), today, now)
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    repo.finish_log(log_id, status="success", players_updated=result.players_updated, api_calls=guard.summary())
    print(f"daily_sync {today} : {result.recommendations} recos, plan {result.plan_nights} soirées, "
          f"{len(result.warnings)} avertissement(s)")
    for w in result.warnings:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
