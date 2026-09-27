"""Entrées pures du moteur de décision (S6, défense, recent_logs, séries) :
extrait de `engine.jobs.daily_sync.run` pour être partagé avec le backtest.

Aucune I/O ici : tout ce qui est chargement (repo) ou écriture reste dans
`daily_sync.run` ; cette fonction ne fait que transformer des données déjà
en mémoire en `DecisionInputs`.
"""
from collections import defaultdict
from datetime import date

from engine.rules.availability import PickRow, SecondChance, SeriesRow
from engine.rules.calendar import Night
from engine.stats.availability_prob import HARD_OUT_STATUSES
from engine.stats.blowout import calibrate
from engine.stats.elo import EloParams, adjusted, as_date, expected_margin, ratings_before, START_RATING, team_shares
from engine.stats.profile import GameLog, PlayerProfile, build_profile, prior_minutes, role_scales
from engine.stats.team_defense import defense_factors
from engine.strategy.config import BLOWOUT_ENABLED
from engine.strategy.regular import DecisionInputs

RECENT_LOGS_WINDOW = 5


def build_decision_inputs(
    *,
    today: date,
    players: dict[int, dict],
    games: list[dict],
    season_games: list[dict],
    logs: list[GameLog],
    season: str,
    prior: str,
    picks: list[PickRow],
    second_chances: list[SecondChance],
    series_rows: list[dict],
    nights: list[Night],
    blowout: bool = BLOWOUT_ENABLED,
    elo_params: EloParams = EloParams(),
) -> tuple[DecisionInputs, dict[int, PlayerProfile]]:
    """Profils (S6, role_scales), défense, recent_logs, lignes de séries :
    tout ce que daily_sync calculait entre le chargement des données et
    decide(). Pure : aucune I/O.

    `logs` = logs des saisons `season` et `prior` mélangés (séparés ici via
    `GameLog.season`). `games` = fenêtre de calendrier autour de `today`
    (devient `DecisionInputs.games`, tel quel). `season_games` = tous les
    matchs de `season` et `prior` (nécessaire à `defense_factors`, qui doit
    pouvoir retrouver n'importe quel match référencé par un log de la
    saison, pas seulement ceux de la fenêtre proche de `today`).

    `blowout` (facteur « écart de force », L3a §2) : si vrai, notes Elo
    d'avant `today` (`ratings_before`, aucun match de `today` ni après),
    écart attendu de chaque match de `games` (`DecisionInputs.expected_margins`)
    et modèle calibré sur les logs/matchs d'avant `today`
    (`DecisionInputs.blowout_model`, à passer explicitement à `decide`). Si
    faux, rien de tout cela n'est calculé : entrées identiques à avant L3a.
    """
    current_by_player: dict[int, list[GameLog]] = defaultdict(list)
    prior_by_player: dict[int, list[GameLog]] = defaultdict(list)
    for log in logs:
        (current_by_player if log.season == season else prior_by_player)[log.player_id].append(log)

    rosters: dict[str, list[int]] = defaultdict(list)
    for pid, p in players.items():
        if p.get("active", True):
            rosters[p["team"]].append(pid)
    scales = role_scales(prior_minutes([l for l in logs if l.season == prior]), rosters)
    profiles = {pid: build_profile(pid, current_by_player[pid], prior_by_player[pid], scales.get(p["team"], 1.0))
                for pid, p in players.items() if p.get("active", True)}

    games_by_id = {g["id"]: g for g in season_games}
    defense = defense_factors([l for l in logs if l.season == season], [l for l in logs if l.season == prior],
                              games_by_id, {pid: p.get("position", "F") for pid, p in players.items()})

    recent_logs = {pid: [{"minutes": l.minutes}
                        for l in sorted(pid_logs, key=lambda l: l.date, reverse=True)[:RECENT_LOGS_WINDOW]]
                  for pid, pid_logs in current_by_player.items()}

    series = [SeriesRow(s["season"], s["round"], s["home_team"], s["away_team"],
                        s.get("home_wins") or 0, s.get("away_wins") or 0, s["status"]) for s in series_rows]

    margins: dict[str, float] = {}
    model = None
    if blowout:
        margins = expected_margins(today=today, players=players, games=games, season_games=season_games,
                                   logs=logs, p=elo_params)
        model = calibrate(logs, season_games, today)

    inputs = DecisionInputs(today=today, nights=nights, games=games, players=players,
                            profiles=profiles, recent_logs=recent_logs, defense=defense,
                            picks=picks, second_chances=second_chances, series=series,
                            x2_used_months=frozenset((p.date.year, p.date.month) for p in picks
                                                     if p.is_x2 and p.mode == "regular"),
                            expected_margins=margins, blowout_model=model)
    return inputs, profiles


def absent_shares(*, today: date, players: dict[int, dict], logs: list[GameLog]) -> dict[str, float]:
    """Part de production des absents (statut `HARD_OUT_STATUSES` ce soir)
    par équipe, calculée seulement pour les équipes ayant au moins un absent.
    En backtest (`dnp_oracle`), les joueurs sans minutes le soir D sont
    marqués « Out » : même chemin."""
    out_by_team: dict[str, set[int]] = defaultdict(set)
    for pid, row in players.items():
        if row.get("injury_status") in HARD_OUT_STATUSES and row.get("team"):
            out_by_team[row["team"]].add(pid)
    if not out_by_team:
        return {}
    logs_by_team: dict[str, list[GameLog]] = defaultdict(list)
    for log in logs:
        if log.team in out_by_team:
            logs_by_team[log.team].append(log)
    result = {}
    for team, out in out_by_team.items():
        shares = team_shares(logs_by_team[team], team, today)
        result[team] = sum(shares.get(pid, 0.0) for pid in out)
    return result


def expected_margins(*, today: date, players: dict[int, dict], games: list[dict], season_games: list[dict],
                     logs: list[GameLog], p: EloParams) -> dict[str, float]:
    """Écart attendu (domicile − extérieur) de chaque match de `games`, par
    id, avec les notes d'avant `today` (aucun résultat de `today` ni après).
    Correction blessures (`adjusted`) seulement pour les matchs de `today`
    (les statuts décrivent ce soir) et seulement si `p.elo_per_share` ≠ 0
    (sinon résultat identique, sans le coût de `team_shares`)."""
    ratings = ratings_before(season_games, today, p)
    absent = absent_shares(today=today, players=players, logs=logs) if p.elo_per_share else {}
    out: dict[str, float] = {}
    for g in games:
        home, away = g["home_team"], g["away_team"]
        r_home, r_away = ratings.get(home, START_RATING), ratings.get(away, START_RATING)
        if as_date(g["date"]) == today:
            r_home = adjusted(r_home, absent.get(home, 0.0), p)
            r_away = adjusted(r_away, absent.get(away, 0.0), p)
        out[str(g.get("id"))] = expected_margin(r_home, r_away, p)
    return out
