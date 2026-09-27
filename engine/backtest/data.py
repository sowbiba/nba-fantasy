"""Données du backtest : chargement d'une saison une seule fois (lecture
seule) et vues « connu avant D » sans fuite du futur.

`SeasonData` gèle un instantané de la saison (matchs, logs de la saison et
de la précédente, vrais picks). Les fonctions `*_before`/`score_on`/
`played_on` ne regardent jamais un log daté >= D : c'est la garantie contre
la fuite que la simulation (tâche 6) doit pouvoir vérifier.

`players` porte les effectifs ACTUELS (2026-27) : ne jamais faire confiance à
`players[...]["team"]` pour une date passée, toujours passer par
`team_before`/`roster_before` (qui lisent `game_logs.team`).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import cached_property

from engine.rules.calendar import Night, build_nights
from engine.rules.game_types import previous_season
from engine.stats.profile import GameLog


@dataclass(frozen=True)
class SeasonData:
    season: str
    prior: str
    players: dict[int, dict]      # id -> {id, name, position} (équipe NON fiable : effectifs actuels)
    games: list[dict]             # games de la saison (id, date, home_team, away_team, game_type, tip_off, status)
    logs: list[GameLog]           # saison + saison précédente
    picks: list[dict]             # vrais picks de l'utilisateur (date, player_id, actual_score, is_x2, mode)
    second_chances: list[dict]

    # Index calculés paresseusement (la simulation, tâche 6, appelle
    # team_before/score_on/played_on par joueur et par soirée : un scan de
    # tous les logs à chaque appel serait O(joueurs × soirées × logs)).
    # `cached_property` écrit dans `__dict__` directement, ce qui fonctionne
    # même sur un dataclass frozen.
    @cached_property
    def _logs_by_player(self) -> dict[int, list[GameLog]]:
        by: dict[int, list[GameLog]] = defaultdict(list)
        for log in self.logs:
            by[log.player_id].append(log)
        for entries in by.values():
            entries.sort(key=lambda l: l.date)
        return by

    @cached_property
    def _log_by_player_date(self) -> dict[tuple[int, date], GameLog]:
        return {(log.player_id, log.date): log for log in self.logs}


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def load_season(repo, season: str) -> SeasonData:
    """Charge toutes les données nécessaires au backtest d'une saison, en
    lecture seule et paginée (méthodes `SupabaseRepo.load_*`)."""
    prior = previous_season(season)
    players = {p["id"]: {"id": p["id"], "name": p.get("name"), "position": p.get("position")}
              for p in repo.load_players()}
    games = repo.load_games_of_seasons([season])
    logs = [GameLog.from_row(r) for r in repo.load_game_logs([season, prior])]
    picks = repo.load_picks(season)
    second_chances = repo.load_second_chances()
    return SeasonData(season=season, prior=prior, players=players, games=games,
                      logs=logs, picks=picks, second_chances=second_chances)


def logs_before(data: SeasonData, d: date) -> list[GameLog]:
    """Logs strictement antérieurs à `d` (le jour même n'est jamais connu à
    l'avance : R7/évite la fuite)."""
    return [l for l in data.logs if l.date < d]


def team_before(data: SeasonData, player_id: int, d: date) -> str | None:
    """Dernière équipe connue avant d (dernier log < d) ; si aucun log avant d
    cette saison, première équipe de la saison ; None si aucun log."""
    season_logs = [l for l in data._logs_by_player.get(player_id, ()) if l.season == data.season]
    if not season_logs:
        return None
    before = [l for l in season_logs if l.date < d]
    if before:
        return before[-1].team
    return season_logs[0].team


def roster_before(data: SeasonData, d: date, window_days: int = 30) -> dict[int, dict]:
    """Joueurs actifs vus avant d : ayant un log dans la saison courante (ou
    la précédente pour le début de saison), avec `team` = team_before et
    `injury_status` = None."""
    game_dates = [_as_date(g["date"]) for g in data.games]
    season_start = min(game_dates) if game_dates else d
    early_season = (d - season_start).days < window_days

    seasons = {data.season} | ({data.prior} if early_season else set())
    seen: set[int] = {l.player_id for l in data.logs if l.season in seasons and l.date < d}

    roster: dict[int, dict] = {}
    for pid in seen:
        player = data.players.get(pid)
        if player is None:
            continue
        roster[pid] = {**player, "team": team_before(data, pid, d), "injury_status": None}
    return roster


def eligible_nights(data: SeasonData, start: date, end: date) -> list[Night]:
    """Soirées éligibles entre `start` et `end` inclus. Ne plafonne jamais en
    interne au-delà de `end` : la simulation (tâche 6) peut demander une
    fenêtre de plusieurs semaines devant D pour la logique de mois forcé du
    planificateur."""
    games = [g for g in data.games if start <= _as_date(g["date"]) <= end]
    return build_nights(games, [])


def score_on(data: SeasonData, player_id: int, d: date) -> int:
    """ttfl_score du log de ce soir, 0 si absent ou 0 minute (R7)."""
    log = data._log_by_player_date.get((player_id, d))
    if log is None:
        return 0
    return log.ttfl if log.minutes > 0 else 0


def played_on(data: SeasonData, player_id: int, d: date) -> bool:
    """Log avec minutes > 0 pour ce soir."""
    log = data._log_by_player_date.get((player_id, d))
    return log is not None and log.minutes > 0
