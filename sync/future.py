"""Compute a player's best future opportunity by scanning the next N days
of scheduled games. Used by the burn-or-save decision.
"""
from datetime import date, datetime, timedelta

from sync.scoring import compute_performance_score


LEAGUE_AVG_TTFL_AT_POSITION = 40  # rough default until per-position stats are populated

_FR_DAYS = {
    "Monday": "lundi", "Tuesday": "mardi", "Wednesday": "mercredi",
    "Thursday": "jeudi", "Friday": "vendredi", "Saturday": "samedi",
    "Sunday": "dimanche",
}


def _describe_game(game: dict, player_team: str) -> str:
    is_home = game["home_team"] == player_team
    opponent = game["away_team"] if is_home else game["home_team"]
    try:
        d = datetime.strptime(game["date"], "%Y-%m-%d").date()
        day_str = _FR_DAYS.get(d.strftime("%A"), d.strftime("%A")).lower()
    except (ValueError, TypeError):
        day_str = game.get("date", "")
    location = "🏠 domicile" if is_home else "✈️ extérieur"
    game_num = game.get("game_number")
    game_label = f"Game {game_num}" if game_num else "match"
    return f"{game_label} vs {opponent} à {location} ({day_str})"


def _opponent_ttfl_at_position(
    team_defense_cache: dict[str, dict],
    opponent: str,
    position: str,
) -> float:
    opp_def = team_defense_cache.get(opponent)
    if not opp_def:
        return LEAGUE_AVG_TTFL_AT_POSITION
    if position == "G":
        val = opp_def.get("vs_guards_ttfl_avg")
    elif position == "F":
        val = opp_def.get("vs_forwards_ttfl_avg")
    else:
        val = opp_def.get("vs_centers_ttfl_avg")
    return val if val else LEAGUE_AVG_TTFL_AT_POSITION


def compute_best_future_opportunity(
    player: dict,
    player_recent_scores: list[int | float],
    future_games: list[dict],
    team_defense_cache: dict[str, dict],
    today: date,
    days_ahead: int = 7,
) -> tuple[float, str | None]:
    """Scan future_games for this player's team over the next `days_ahead` days
    and return (best_score, description_of_best_spot).

    Callers should prefetch `future_games` (all games in window) and
    `team_defense_cache` (tricode → row) to avoid per-call DB roundtrips.
    """
    player_team = player["team"]
    player_season_avg = player.get("avg_ttfl_season", 0) or 0
    if player_season_avg == 0:
        return 0, None

    cutoff_iso = (today + timedelta(days=days_ahead)).isoformat()
    today_iso = today.isoformat()
    best_score = 0.0
    best_desc: str | None = None

    candidates = [
        g for g in future_games
        if (g["home_team"] == player_team or g["away_team"] == player_team)
        and g["date"] > today_iso
        and g["date"] <= cutoff_iso
    ]

    for game in candidates:
        is_home = game["home_team"] == player_team
        opponent = game["away_team"] if is_home else game["home_team"]
        opp_ttfl = _opponent_ttfl_at_position(team_defense_cache, opponent, player["position"])

        try:
            game_dt = datetime.strptime(game["date"], "%Y-%m-%d").date()
            est_days_rest = max(1, (game_dt - today).days)
        except (ValueError, TypeError):
            est_days_rest = 2

        perf_score = compute_performance_score(
            avg_l5=player.get("avg_ttfl_l5", 0) or 0,
            avg_l10=player.get("avg_ttfl_l10", 0) or 0,
            avg_l20=player.get("avg_ttfl_l20", 0) or 0,
            opponent_ttfl_at_position=opp_ttfl,
            league_avg_ttfl_at_position=LEAGUE_AVG_TTFL_AT_POSITION,
            home_avg=player.get("home_avg", 0) or 0,
            away_avg=player.get("away_avg", 0) or 0,
            season_avg=player_season_avg,
            is_home=is_home,
            days_rest=est_days_rest,
            recent_scores=player_recent_scores,
            stddev=player.get("stddev_ttfl", 0) or 0,
        )

        if perf_score > best_score:
            best_score = perf_score
            best_desc = _describe_game(game, player_team)

    return best_score, best_desc
