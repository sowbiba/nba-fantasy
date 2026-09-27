"""Job quotidien (GitHub Actions, plusieurs fois/jour) : statuts et scores
ESPN, scoring des picks, blessures, soirées, recommandations du soir, plan
30 jours, Elo des équipes et prédictions de match (`team_elo` /
`game_predictions`, L3a).

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
from engine.rules.availability import PickRow, SecondChance
from engine.rules.calendar import PARIS, build_nights
from engine.rules.game_types import is_eligible, previous_season, season_for_date
from engine.stats.aggregates import player_aggregates
from engine.stats.elo import EloParams, game_season, is_countable, predict, ratings_before
from engine.stats.profile import GameLog
from engine.strategy.inputs import absent_shares, build_decision_inputs
from engine.strategy.regular import HORIZON_DAYS, decide

SCHEDULE_PAST_DAYS = 5
SCHEDULE_AHEAD_DAYS = 35
PLAN_RETENTION = timedelta(days=7)
PREDICTION_WINDOW_DAYS = 14   # matchs à venir couverts par game_predictions (spec L3a §3)
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


def team_elo_rows(season_games: list[dict], today: date, season: str, ratings: dict[str, float],
                  now: datetime) -> list[dict]:
    """Lignes `team_elo` : note de chaque équipe vue par `ratings` (déjà
    calculées après tous les matchs terminés jusqu'à `today` inclus), et le
    nombre de matchs comptables JOUÉS CETTE SAISON jusqu'à `today` inclus
    (mêmes règles que `ratings_before` : `is_countable`, date < today + 1
    jour ; `games` ne compte pas la saison précédente — `season_games`
    mélange saison courante et précédente, cf. `run` — sinon la colonne
    afficherait ~82 matchs dès le soir d'ouverture)."""
    cutoff = today + timedelta(days=1)
    games_played: dict[str, int] = defaultdict(int)
    for g in season_games:
        if is_countable(g) and game_season(g) == season and _d(g["date"]) < cutoff:
            games_played[g["home_team"]] += 1
            games_played[g["away_team"]] += 1
    return [{"team": team, "rating": round(rating, 2), "games": games_played.get(team, 0),
             "updated_at": now.isoformat()} for team, rating in ratings.items()]


def game_prediction_rows(window: list[dict], today: date, ratings: dict[str, float],
                         absent: dict[str, float], p: EloParams, now: datetime) -> list[dict]:
    """Lignes `game_predictions` pour les matchs à venir ÉLIGIBLES (R11/R12 :
    saison régulière, `cup_final`, playoffs — pas de préparation/all-star,
    que l'Elo ne voit jamais) et non terminés de la fenêtre `today` →
    `today + PREDICTION_WINDOW_DAYS` jours, avec la correction blessures des
    statuts ACTUELS (`absent`, calculée une seule fois pour toute la
    fenêtre : c'est la meilleure information disponible au moment de la
    synchro, même si elle ne dit presque rien d'un match dans 10 jours —
    spec L3a §3)."""
    horizon = today + timedelta(days=PREDICTION_WINDOW_DAYS)
    upcoming = [g for g in window if g.get("status") != "final" and is_eligible(g.get("game_type", "unknown"))
               and today <= _d(g["date"]) <= horizon]
    rows = []
    for g in upcoming:
        pred = predict(g, ratings, absent, p)
        rows.append({"game_id": pred.game_id, "home_rating": round(pred.home_rating, 2),
                     "away_rating": round(pred.away_rating, 2), "home_win_prob": round(pred.home_win_prob, 4),
                     "expected_margin": round(pred.expected_margin, 2), "updated_at": now.isoformat()})
    return rows


def _write_elo(repo, season_games: list[dict], window: list[dict], today: date, season: str,
              players: dict[int, dict], all_logs: list[GameLog], elo_params: EloParams,
              now: datetime) -> None:
    """Note Elo de chaque équipe et prédictions des matchs à venir (L3a §3).
    Appelée via `_step` par `run` : une panne d'écriture ici (table absente,
    erreur transitoire) ne doit jamais empêcher les recommandations et le
    plan du soir d'être écrits — ce sont eux qui comptent le plus pour
    l'utilisateur, l'Elo n'est qu'un affichage connecté additionnel."""
    ratings = ratings_before(season_games, today + timedelta(days=1), elo_params)
    team_rows = team_elo_rows(season_games, today, season, ratings, now)
    if team_rows:
        repo.upsert_team_elo(team_rows)
    absent = absent_shares(today=today, players=players, logs=all_logs)
    pred_rows = game_prediction_rows(window, today, ratings, absent, elo_params, now)
    if pred_rows:
        repo.upsert_game_predictions(pred_rows)


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


def run(repo, fetch_scoreboard, fetch_injuries, today: date, now: datetime,
       elo_params: EloParams = EloParams()) -> RunResult:
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
    season_games = repo.load_games_of_seasons([season, prior])
    all_logs = [GameLog.from_row(r) for r in repo.load_game_logs([season, prior])]
    current_by_player: dict[int, list[GameLog]] = defaultdict(list)
    for log in all_logs:
        if log.season == season:
            current_by_player[log.player_id].append(log)

    aggregate_rows = [{**{k: p[k] for k in IDENTITY}, **player_aggregates(current_by_player[pid])}
                      for pid, p in players.items() if current_by_player[pid]]
    if aggregate_rows:
        repo.upsert_players(aggregate_rows)
    result.players_updated = len(aggregate_rows)

    window = repo.load_games_between(today - timedelta(days=SCHEDULE_PAST_DAYS), today + timedelta(days=SCHEDULE_AHEAD_DAYS))

    _step("elo", lambda: _write_elo(repo, season_games, window, today, season, players, all_logs,
                                    elo_params, now), result)

    series_rows = repo.load_series(season)
    nights = [n for n in build_nights([g for g in window if _d(g["date"]) >= today], series_rows)]
    repo.replace_nights(today, [{"date": n.date.isoformat(), "season": n.season, "mode": n.mode,
                                 "n_eligible_games": n.n_eligible_games, "closing_at": n.closing_at.isoformat(),
                                 "is_phantom": n.is_phantom, "updated_at": now.isoformat()} for n in nights])

    picks = [PickRow(p["id"], p["player_id"], _d(p["date"]), p["mode"], p["season"], bool(p.get("is_x2")))
             for p in repo.load_picks(season)]
    second_chances = [SecondChance(s["pick_id"], s["player_id"], _d(s["bought_on"]), _d(s["expires_on"]))
                      for s in repo.load_second_chances()]
    decision_inputs, _profiles = build_decision_inputs(
        today=today, players=players, games=window, season_games=season_games, logs=all_logs,
        season=season, prior=prior, picks=picks, second_chances=second_chances,
        series_rows=series_rows, nights=nights,
    )
    decision = decide(decision_inputs, blowout=decision_inputs.blowout_model)   # None sauf BLOWOUT_ENABLED

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

    plan_rows = [{"generated_at": now.isoformat(), "night": night.isoformat(), "player_id": e.cell.player_id,
                  "is_x2": e.is_x2, "projection": round(e.cell.projection, 1), "p_play": round(e.cell.p_play, 3),
                  "value": round(e.cell.value, 1), "explanation": plan_explanation(e.cell)}
                 for night, e in decision.plan.items() if (night - today).days < HORIZON_DAYS]
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
