"""Simulation soir par soir d'une saison passée (L2b).

Pour chaque soirée éligible D, le moteur ne voit que ce qui était connu
avant D (`logs_before`, `roster_before`), décide avec l'historique de picks
SIMULÉS de la stratégie (cooldown R3, x2 déjà posés), puis le pick est noté
avec le vrai résultat du soir (`score_on`) : DNP → 0 et cooldown consommé
(R7), x2 doublant le score même négatif et perdu sur DNP (R10). La moyenne
compte chaque soirée éligible, avec ou sans pick (R14). `seed_picks` amorce
cet historique simulé avec les vrais picks de l'utilisateur antérieurs à la
fenêtre, pour démarrer sous les mêmes contraintes (cooldown, x2 du mois) —
voir `simulate`.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from engine.backtest.data import (
    SeasonData,
    eligible_nights,
    logs_before,
    played_on,
    roster_before,
    score_on,
)
from engine.rules.availability import PickRow
from engine.strategy.inputs import build_decision_inputs
from engine.strategy.regular import decide
from engine.strategy.value import X2_MONTHS

STRATEGIES = ("best_available", "plan")
INJURY_MODES = ("none", "dnp_oracle")
GAMES_PAST_DAYS = 5      # comme daily_sync (SCHEDULE_PAST_DAYS) : jours de repos
GAMES_AHEAD_DAYS = 35    # comme daily_sync : le planificateur a besoin de voir la fin du mois
ORACLE_RECENT_GAMES = 5


@dataclass(frozen=True)
class NightResult:
    night: date
    player_id: int | None
    is_x2: bool
    points: int            # score × 2 si x2 (négatif compris), 0 si pas de pick ou DNP


@dataclass(frozen=True)
class BacktestResult:
    strategy: str          # "best_available" | "plan" | "user"
    injury_mode: str       # "none" | "dnp_oracle"
    nights: list[NightResult]

    @property
    def total(self) -> int:
        return sum(n.points for n in self.nights)

    @property
    def average(self) -> float:
        """R14 : total / nombre de soirées éligibles (sans pick = 0)."""
        return self.total / len(self.nights) if self.nights else 0.0

    @property
    def zeros(self) -> int:
        return sum(1 for n in self.nights if n.points == 0)

    @property
    def x2_gain(self) -> int:
        """Points apportés par les x2 : score doublé − score simple = score."""
        return sum(n.points // 2 for n in self.nights if n.is_x2)


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _month(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _last_regular_night_of_month(data: SeasonData) -> dict[tuple[int, int], date]:
    """Dernière soirée éligible de SR de chaque mois, sur tout le calendrier
    de la saison (le calendrier est connu à l'avance : pas une fuite)."""
    dates = [_as_date(g["date"]) for g in data.games]
    if not dates:
        return {}
    last: dict[tuple[int, int], date] = {}
    for n in eligible_nights(data, min(dates), max(dates)):
        if n.mode == "regular" and not n.is_phantom and n.n_eligible_games > 0:
            last[_month(n.date)] = max(last.get(_month(n.date), n.date), n.date)
    return last


def _x2_allowed(night_mode: str, d: date, used: set[tuple[int, int]]) -> bool:
    return night_mode == "regular" and d.month in X2_MONTHS and _month(d) not in used


def _players_at(data: SeasonData, d: date, injury_mode: str) -> dict[int, dict]:
    """Effectif « avant D » : équipe via game_logs (jamais la table players,
    qui porte les effectifs actuels), joueurs sans équipe de la saison exclus.
    `dnp_oracle` : pour D seulement, un joueur ayant joué au moins un de ses 5
    derniers matchs et absent ce soir est déclaré « Out »."""
    players = {pid: dict(p) for pid, p in roster_before(data, d).items() if p.get("team") is not None}
    if injury_mode == "dnp_oracle":
        for pid, p in players.items():
            recent = [l for l in reversed(data._logs_by_player.get(pid, ())) if l.date < d][:ORACLE_RECENT_GAMES]
            if any(l.minutes > 0 for l in recent) and not played_on(data, pid, d):
                p["injury_status"] = "Out"
    return players


def simulate(data: SeasonData, start: date, end: date, strategy: str, injury_mode: str = "none",
             decay: float | None = None, seed_picks: Iterable[PickRow] = ()) -> BacktestResult:
    """`seed_picks` (optionnel, backtest uniquement) : picks RÉELS de
    l'utilisateur antérieurs à `start` (typiquement les 30 jours qui
    précèdent), pour que la simulation démarre sous les mêmes contraintes
    que l'utilisateur — cooldown R3 (dans les deux sens, comme
    `is_available`) et x2 déjà posé ce mois-ci (R10 : un seul x2/mois). Ils
    ne sont jamais notés ni renvoyés dans `results` : seules les soirées de
    `[start, end]` comptent."""
    if strategy not in STRATEGIES:
        raise ValueError(f"stratégie inconnue : {strategy}")
    if injury_mode not in INJURY_MODES:
        raise ValueError(f"mode blessures inconnu : {injury_mode}")

    last_of_month = _last_regular_night_of_month(data)
    history: list[PickRow] = list(seed_picks)   # amorcé par les vrais picks pré-fenêtre, puis picks simulés
    x2_used: set[tuple[int, int]] = {_month(p.date) for p in history if p.is_x2}
    results: list[NightResult] = []

    for night in eligible_nights(data, start, end):
        if night.is_phantom or night.n_eligible_games <= 0:
            continue
        d = night.date
        horizon_end = d + timedelta(days=GAMES_AHEAD_DAYS)
        window_start = d - timedelta(days=GAMES_PAST_DAYS)
        inputs, _profiles = build_decision_inputs(
            today=d,
            players=_players_at(data, d, injury_mode),
            games=[g for g in data.games if window_start <= _as_date(g["date"]) <= horizon_end],
            season_games=data.games,
            logs=logs_before(data, d),
            season=data.season,
            prior=data.prior,
            picks=list(history),
            # Les secondes chances réelles portent les pick_id de l'utilisateur :
            # elles n'ont pas de sens sur l'historique simulé.
            second_chances=[],
            series_rows=[],
            nights=eligible_nights(data, d, horizon_end),
        )
        decision = decide(inputs, tonight_source=strategy, decay=decay)

        if not decision.recommendations:
            results.append(NightResult(d, None, False, 0))
            continue
        pid = decision.recommendations[0].cell.player_id
        if strategy == "plan":
            entry = decision.plan.get(d)
            is_x2 = (entry is not None and entry.cell.player_id == pid and entry.is_x2
                     and _x2_allowed(night.mode, d, x2_used))
        else:
            # Référence naïve : x2 sur la dernière soirée éligible du mois.
            is_x2 = last_of_month.get(_month(d)) == d and _x2_allowed(night.mode, d, x2_used)

        points = score_on(data, pid, d) * (2 if is_x2 else 1)   # DNP → 0, x2 perdu (R7, R10)
        results.append(NightResult(d, pid, is_x2, points))
        history.append(PickRow(len(history) + 1, pid, d, night.mode, data.season, is_x2))
        if is_x2:
            x2_used.add(_month(d))

    return BacktestResult(strategy, injury_mode, results)


def user_result(data: SeasonData, start: date, end: date) -> BacktestResult:
    """Vrais picks de l'utilisateur sur la même fenêtre, notés comme la
    simulation (score_on × 2 si x2) pour une comparaison à l'identique."""
    by_date: dict[date, dict] = {}
    for p in data.picks:
        d = _as_date(p["date"])
        if d not in by_date or (p.get("id") or 0) > (by_date[d].get("id") or 0):
            by_date[d] = p
    results = []
    for night in eligible_nights(data, start, end):
        if night.is_phantom or night.n_eligible_games <= 0:
            continue
        pick = by_date.get(night.date)
        if pick is None:
            results.append(NightResult(night.date, None, False, 0))
            continue
        is_x2 = bool(pick.get("is_x2"))
        pid = int(pick["player_id"])
        results.append(NightResult(night.date, pid, is_x2, score_on(data, pid, night.date) * (2 if is_x2 else 1)))
    return BacktestResult("user", "none", results)
