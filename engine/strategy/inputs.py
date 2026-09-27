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
from engine.stats.profile import GameLog, PlayerProfile, build_profile, prior_minutes, role_scales
from engine.stats.team_defense import defense_factors
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

    inputs = DecisionInputs(today=today, nights=nights, games=games, players=players,
                            profiles=profiles, recent_logs=recent_logs, defense=defense,
                            picks=picks, second_chances=second_chances, series=series)
    return inputs, profiles
