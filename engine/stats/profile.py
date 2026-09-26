"""Profil d'un joueur : efficacité (TTFL/min), minutes de rôle, régularité,
taux de présence, avec le prior de la saison précédente fondu au fil des
matchs de la saison en cours (S6).

Efficacité et minutes de rôle sont mesurées sur les matchs JOUÉS : l'absence
est portée par P(joue), jamais par la projection (sinon double compte).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev

RECENCY = 0.9                # poids 0.9^i, du plus récent au plus ancien
EFFICIENCY_GAMES = 15        # fenêtre d'efficacité (matchs joués)
ROLE_GAMES = 8               # fenêtre des minutes de rôle (matchs joués)
PRESENCE_GAMES = 15          # fenêtre du taux de présence (tous les logs)
PRIOR_K = 10                 # à 10 matchs joués, prior et saison pèsent autant
ROOKIE_TTFL_PER_MIN = 0.55
ROOKIE_MINUTES = 12.0
TEAM_MINUTES = 240.0
ROTATION_SIZE = 10
ROLE_SCALE_BOUNDS = (0.85, 1.15)
PRESENCE_BOUNDS = (0.5, 1.0)
DEFAULT_PRESENCE = 0.9


@dataclass(frozen=True)
class GameLog:
    player_id: int
    game_id: str
    date: date
    season: str
    team: str
    minutes: int
    ttfl: int
    is_home: bool

    @classmethod
    def from_row(cls, row: dict) -> "GameLog":
        d = row["date"]
        return cls(
            player_id=int(row["player_id"]), game_id=str(row["game_id"]),
            date=d if isinstance(d, date) else date.fromisoformat(str(d)[:10]),
            season=row.get("season") or "", team=row.get("team") or "",
            minutes=int(row.get("minutes") or 0), ttfl=int(row.get("ttfl_score") or 0),
            is_home=bool(row.get("is_home")),
        )


@dataclass(frozen=True)
class PlayerProfile:
    player_id: int
    ttfl_per_min: float
    exp_minutes: float
    games_current: int
    stddev: float
    availability_rate: float

    @property
    def base(self) -> float:
        return self.ttfl_per_min * self.exp_minutes


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _recent_first(logs: list[GameLog]) -> list[GameLog]:
    return sorted(logs, key=lambda l: l.date, reverse=True)


def _efficiency(played: list[GameLog]) -> float | None:
    window = played[:EFFICIENCY_GAMES]
    weights = [RECENCY ** i for i in range(len(window))]
    minutes = sum(w * l.minutes for w, l in zip(weights, window))
    if minutes <= 0:
        return None
    return sum(w * l.ttfl for w, l in zip(weights, window)) / minutes


def _role_minutes(played: list[GameLog]) -> float | None:
    window = played[:ROLE_GAMES]
    if not window:
        return None
    weights = [RECENCY ** i for i in range(len(window))]
    return sum(w * l.minutes for w, l in zip(weights, window)) / sum(weights)


def prior_minutes(prior_logs: list[GameLog]) -> dict[int, float]:
    by_player: dict[int, list[int]] = defaultdict(list)
    for log in prior_logs:
        if log.minutes > 0:
            by_player[log.player_id].append(log.minutes)
    return {pid: mean(mins) for pid, mins in by_player.items()}


def role_scales(prior_mins: dict[int, float], rosters: dict[str, list[int]]) -> dict[str, float]:
    """Échelle des minutes de la saison passée dans l'effectif actuel : une
    équipe qui a perdu sa star redistribue (> 1), un effectif encombré
    partage (< 1). Rotation = les 10 plus gros minutages passés."""
    scales = {}
    for team, ids in rosters.items():
        top = sorted((prior_mins.get(pid, 0.0) for pid in ids), reverse=True)[:ROTATION_SIZE]
        total = sum(top)
        scales[team] = 1.0 if total <= 0 else _clamp(TEAM_MINUTES / total, ROLE_SCALE_BOUNDS)
    return scales


def build_profile(player_id: int, current_logs: list[GameLog], prior_logs: list[GameLog],
                  role_scale: float = 1.0) -> PlayerProfile:
    current = _recent_first(current_logs)
    played = [l for l in current if l.minutes > 0]
    prior_played = [l for l in prior_logs if l.minutes > 0]

    if prior_played:
        prior_eff = sum(l.ttfl for l in prior_played) / sum(l.minutes for l in prior_played)
        prior_min = mean(l.minutes for l in prior_played) * role_scale
    else:
        prior_eff, prior_min = ROOKIE_TTFL_PER_MIN, ROOKIE_MINUTES

    n = len(played)
    weight = n / (n + PRIOR_K)
    eff_current = _efficiency(played)
    min_current = _role_minutes(played)
    ttfl_per_min = prior_eff if eff_current is None else weight * eff_current + (1 - weight) * prior_eff
    exp_minutes = prior_min if min_current is None else weight * min_current + (1 - weight) * prior_min

    sample = [l.ttfl for l in (played or _recent_first(prior_played))][:20]
    stddev = pstdev(sample) if len(sample) >= 3 else 0.0

    recent = current[:PRESENCE_GAMES]
    presence = (_clamp(sum(1 for l in recent if l.minutes > 0) / len(recent), PRESENCE_BOUNDS)
                if recent else DEFAULT_PRESENCE)

    return PlayerProfile(player_id, ttfl_per_min, exp_minutes, n, stddev, presence)
