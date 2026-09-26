"""R1 (formule TTFL), R10 (bonus x2), R14 (soirée sans pick = 0 réel)."""
from datetime import date


def compute_ttfl_score(
    pts: int, reb: int, ast: int, stl: int, blk: int,
    fgm: int, fga: int, tpm: int, tpa: int, ftm: int, fta: int, tov: int,
) -> int:
    """R1 : PTS+REB+AST+STL+BLK+FGM+3PM+FTM − TOV − tirs, 3pts et LF ratés."""
    positive = pts + reb + ast + stl + blk + fgm + tpm + ftm
    negative = tov + (fga - fgm) + (tpa - tpm) + (fta - ftm)
    return positive - negative


def night_points(actual_score: int | None, is_x2: bool) -> int | None:
    """Points d'une soirée pickée. R10 : le x2 double aussi un score négatif.
    None tant que le pick n'est pas scoré."""
    if actual_score is None:
        return None
    return actual_score * 2 if is_x2 else actual_score


def period_average(
    eligible_nights: list[date],
    results: dict[date, tuple[int | None, bool]],
) -> float | None:
    """Moyenne sur les soirées éligibles déjà scorables.

    R14 : une soirée éligible sans pick compte 0. Une soirée dont le pick
    n'est pas encore scoré (actual_score None) est exclue du calcul.
    `results` : date → (actual_score, is_x2).
    """
    total = 0
    counted = 0
    for night in eligible_nights:
        actual, is_x2 = results.get(night, (0, False))
        points = night_points(actual, is_x2)
        if points is None:
            continue
        total += points
        counted += 1
    return total / counted if counted else None
