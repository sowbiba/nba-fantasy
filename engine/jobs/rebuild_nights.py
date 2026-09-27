"""Reconstruction des soirées (nights) d'une saison passée.

Utilisé pour reconstruire la table `nights` d'une saison passée,
dont les données sont nécessaires pour `period_stats('saison', ...)`
(page Picks de la saison passée).

Ne supprime aucune ligne existante : upsert sur la date uniquement.
N'écrit que les soirées antérieures à aujourd'hui (heure de Paris).
"""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from engine.rules.calendar import PARIS, build_nights

PARIS_TZ = ZoneInfo("Europe/Paris")


def run(repo, season: str, today: date, now: datetime) -> int:
    """Reconstruit les soirées d'une saison.

    Args:
        repo: SupabaseRepo ou FakeRepo
        season: Saison à reconstruire (ex. "2025-26")
        today: Date d'aujourd'hui (Paris)
        now: Heure actuelle (UTC)

    Returns:
        Nombre de soirées écrites.
    """
    games = repo.load_games_of_seasons([season])
    series = repo.load_series(season)

    # Build all nights for the season
    nights = build_nights(games, series)

    # Keep only nights before today (strict)
    past_nights = [n for n in nights if n.date < today]

    # Convert to row dicts
    rows = [
        {
            "date": n.date.isoformat(),
            "season": n.season,
            "mode": n.mode,
            "n_eligible_games": n.n_eligible_games,
            "closing_at": n.closing_at.isoformat(),
            "is_phantom": n.is_phantom,
            "updated_at": now.isoformat(),
        }
        for n in past_nights
    ]

    # Upsert without deleting
    if rows:
        repo.upsert_nights(rows)

    return len(rows)


def main() -> None:
    """Entry point pour `python -m engine.jobs.rebuild_nights --season 2025-26`."""
    import argparse
    from engine.io.repo import SupabaseRepo

    parser = argparse.ArgumentParser(description="Reconstruit les soirées d'une saison passée")
    parser.add_argument("--season", required=True, help="Saison à reconstruire (ex. 2025-26)")
    args = parser.parse_args()

    repo = SupabaseRepo.from_env()
    today = datetime.now(PARIS_TZ).date()
    now = datetime.now(UTC)

    count = run(repo, args.season, today, now)
    print(f"{count} soirées écrites pour {args.season}")


if __name__ == "__main__":
    main()
