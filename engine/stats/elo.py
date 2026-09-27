"""Elo maison des équipes, prédictions de match et correction blessures
(spec `docs/superpowers/specs/2026-09-28-l3a-elo-design.md` §1).

Note de départ 1500 pour une équipe jamais vue. Mise à jour de type
FiveThirtyEight, zéro-somme entre les deux équipes du match (l'avantage du
terrain entre dans la probabilité pré-match, donc dans la mise à jour, mais
la somme des deltas domicile/extérieur reste nulle). Entre deux saisons,
retour partiel vers `p.mean` pour toutes les équipes déjà vues.

Aucune fuite du futur : `ratings_before(games, before, p)` n'utilise que les
matchs terminés (status 'final', scores non nuls, game_type éligible) de
date strictement antérieure à `before`.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from engine.rules.game_types import is_eligible, season_for_date
from engine.stats.profile import GameLog

START_RATING = 1500.0


@dataclass(frozen=True)
class EloParams:
    k: float = 20.0
    home_advantage: float = 70.0
    carryover: float = 0.75          # R ← carryover·R + (1−carryover)·MEAN à chaque nouvelle saison
    mean: float = 1505.0
    elo_per_share: float = 0.0        # correction blessures (0 = désactivée tant que non calibrée)
    points_per_elo: float = 1 / 28


def win_prob(home: float, away: float, p: EloParams) -> float:
    """Probabilité de victoire à domicile, avantage du terrain inclus."""
    return 1.0 / (1.0 + 10 ** (-((home + p.home_advantage - away) / 400.0)))


def expected_margin(home: float, away: float, p: EloParams) -> float:
    """Écart de points attendu (domicile − extérieur), avantage inclus."""
    return (home + p.home_advantage - away) * p.points_per_elo


def mov_multiplier(margin: int, winner_elo_diff: float) -> float:
    """Multiplicateur d'écart de type FiveThirtyEight. `winner_elo_diff` =
    note (avantage du terrain inclus le cas échéant) du vainqueur moins
    celle du vaincu, avant le match — négatif si l'outsider (au sens Elo)
    l'emporte, ce qui augmente le multiplicateur."""
    return ((abs(margin) + 3) ** 0.8) / (7.5 + 0.006 * winner_elo_diff)


def as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def game_season(game: dict) -> str:
    return game.get("season") or season_for_date(as_date(game["date"]))


def is_countable(game: dict) -> bool:
    """Match utilisable par l'Elo : terminé, scores connus, type éligible
    (R11/R12). Public — réutilisé par le rejeu incrémental (`elo_report`,
    tâche 3) pour filtrer/trier les matchs exactement comme `ratings_before`."""
    return (
        game.get("status") == "final"
        and game.get("home_score") is not None
        and game.get("away_score") is not None
        and is_eligible(game.get("game_type", "unknown"))
    )


def apply_season_carryover(ratings: dict[str, float], p: EloParams) -> None:
    """Retour partiel vers `p.mean`, en place, pour toutes les équipes déjà
    vues (changement de saison)."""
    for team in ratings:
        ratings[team] = p.carryover * ratings[team] + (1 - p.carryover) * p.mean


def apply_game(ratings: dict[str, float], game: dict, p: EloParams) -> None:
    """Applique en place le résultat d'un match déjà terminé à `ratings`
    (équipe jamais vue : `START_RATING`). Aucune vérification de date ou de
    type ici : c'est à l'appelant (`ratings_before`, ou le rejeu
    chronologique du job `elo_report`) de garantir l'ordre et l'absence de
    fuite — c'est le petit helper incrémental qui permet de rejouer une
    saison en O(n) plutôt que de rappeler `ratings_before` (O(n)) à chaque
    soirée (O(n²))."""
    home, away = game["home_team"], game["away_team"]
    home_rating = ratings.get(home, START_RATING)
    away_rating = ratings.get(away, START_RATING)

    home_score, away_score = game["home_score"], game["away_score"]
    margin = home_score - away_score
    home_won = margin > 0
    prob_home = win_prob(home_rating, away_rating, p)

    winner_diff = (
        (home_rating + p.home_advantage) - away_rating
        if home_won
        else away_rating - (home_rating + p.home_advantage)
    )
    mult = mov_multiplier(margin, winner_diff)
    actual_home = 1.0 if home_won else 0.0
    delta = p.k * mult * (actual_home - prob_home)

    ratings[home] = home_rating + delta
    ratings[away] = away_rating - delta


def ratings_before(games: list[dict], before: date, p: EloParams) -> dict[str, float]:
    """Notes de toutes les équipes vues, après tous les matchs terminés
    (status 'final', scores non nuls, game_type éligible) de date < before,
    rejoués en ordre (date, id) ; retour vers la moyenne à chaque changement
    de saison rencontré (toutes les équipes déjà vues sont régressées une
    fois, même celles sans match dans la nouvelle saison)."""
    eligible = [g for g in games if is_countable(g) and as_date(g["date"]) < before]
    eligible.sort(key=lambda g: (as_date(g["date"]), g["id"]))

    ratings: dict[str, float] = {}
    current_season: str | None = None

    for game in eligible:
        season = game_season(game)
        if current_season is None:
            current_season = season
        elif season != current_season:
            apply_season_carryover(ratings, p)
            current_season = season

        apply_game(ratings, game, p)

    # `before` peut être en début de saison N+1 alors qu'aucun match de N+1
    # n'a encore été joué (ex. soir d'ouverture) : la boucle ci-dessus n'a
    # alors vu passer aucun changement de saison. Régresse dans ce cas aussi
    # (idempotent avec la boucle : si un match N+1 a déjà été traité,
    # current_season vaut déjà season_for_date(before) et rien ne change).
    if current_season is not None and season_for_date(before) != current_season:
        apply_season_carryover(ratings, p)

    return ratings


def pregame_margins(games: list[dict], before: date, p: EloParams) -> dict[str, float]:
    """Écart attendu d'AVANT-MATCH (domicile − extérieur, avantage du terrain
    inclus, sans correction blessures) de chaque match terminé et comptable
    de date < `before`, par id. Même rejeu chronologique que
    `ratings_before`, mais l'écart est relevé avant `apply_game` et les
    notes sont figées par date : les matchs d'un même soir ne se voient pas
    (l'écart d'un match du soir D = celui qu'aurait donné
    `ratings_before(games, D, p)`)."""
    eligible = [g for g in games if is_countable(g) and as_date(g["date"]) < before]
    eligible.sort(key=lambda g: (as_date(g["date"]), g["id"]))

    ratings: dict[str, float] = {}
    current_season: str | None = None
    out: dict[str, float] = {}
    i = 0
    while i < len(eligible):
        day = as_date(eligible[i]["date"])
        j = i
        while j < len(eligible) and as_date(eligible[j]["date"]) == day:
            j += 1
        batch = eligible[i:j]
        # Même règle de retour vers la moyenne que ratings_before (la saison
        # d'un soir est celle de sa date).
        season = game_season(batch[0])
        if current_season is None:
            current_season = season
        elif season != current_season:
            apply_season_carryover(ratings, p)
            current_season = season
        for g in batch:
            out[str(g["id"])] = expected_margin(ratings.get(g["home_team"], START_RATING),
                                                ratings.get(g["away_team"], START_RATING), p)
        for g in batch:
            apply_game(ratings, g, p)
        i = j
    return out


def team_shares(logs: list[GameLog], team: str, before: date, window: int = 15) -> dict[int, float]:
    """Part de chaque joueur dans la production de l'équipe (minutes ×
    TTFL/min moyen == somme des TTFL, sur ses `window` derniers matchs
    d'équipe avant `before`). Somme = 1 ; {} si aucun log ou production
    totale nulle/négative (TTFL peut être négatif)."""
    team_logs = [l for l in logs if l.team == team and l.date < before]
    if not team_logs:
        return {}

    game_dates = sorted({(l.date, l.game_id) for l in team_logs}, reverse=True)[:window]
    game_ids = {gid for _, gid in game_dates}

    production: dict[int, float] = defaultdict(float)
    for log in team_logs:
        if log.game_id in game_ids:
            production[log.player_id] += log.ttfl

    clamped = {pid: max(0.0, prod) for pid, prod in production.items()}
    total = sum(clamped.values())
    if total <= 0:
        return {}
    return {pid: prod / total for pid, prod in clamped.items()}


def adjusted(rating: float, absent_share: float, p: EloParams) -> float:
    """Note corrigée des absents : réduite proportionnellement à la part de
    production absente."""
    return rating - p.elo_per_share * absent_share


@dataclass(frozen=True)
class GamePrediction:
    game_id: str
    home_rating: float
    away_rating: float
    home_win_prob: float
    expected_margin: float


def predict(game: dict, ratings: dict[str, float], absent_share: dict[str, float],
           p: EloParams) -> GamePrediction:
    """Prédiction d'un match à venir : notes brutes de `ratings` (défaut
    1500 si équipe inconnue), corrigées des absents pour la probabilité et
    l'écart attendu."""
    home, away = game["home_team"], game["away_team"]
    home_rating = ratings.get(home, START_RATING)
    away_rating = ratings.get(away, START_RATING)

    adj_home = adjusted(home_rating, absent_share.get(home, 0.0), p)
    adj_away = adjusted(away_rating, absent_share.get(away, 0.0), p)

    return GamePrediction(
        game_id=game["id"],
        home_rating=home_rating,
        away_rating=away_rating,
        home_win_prob=win_prob(adj_home, adj_away, p),
        expected_margin=expected_margin(adj_home, adj_away, p),
    )
