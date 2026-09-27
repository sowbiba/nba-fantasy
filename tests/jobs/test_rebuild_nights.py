"""Tests pour le job de reconstruction des soirées.

Scénario : une saison avec présaison, play-in et soirées SR (et Cup).
Seules les SR/Cup antérieures à aujourd'hui sont écrites.
Aucune suppression ne doit avoir lieu (upsert sur la date).
"""
from datetime import date, datetime, UTC

import pytest

from engine.jobs.rebuild_nights import run
from tests.jobs.fakes import FakeRepo


TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def _game(gid, d, home, away, game_type, season="2026-27", tip_off=None, status="scheduled"):
    """Helper pour créer un game."""
    return {
        "id": gid,
        "date": d.isoformat(),
        "home_team": home,
        "away_team": away,
        "game_type": game_type,
        "season": season,
        "tip_off": tip_off,
        "status": status,
    }


def test_rebuild_nights_ecrit_uniquement_dates_avant_aujourd_hui():
    """Seules les soirées antérieures à aujourd'hui (strict) sont écrites."""
    before = date(2026, 10, 28)
    day_before_today = date(2026, 11, 1)
    today = TODAY
    after_today = date(2026, 11, 3)

    games = [
        # Preseason (not eligible)
        _game("001262600001", before, "DEN", "LAL", "preseason"),
        # Play-in (not eligible)
        _game("005262600101", day_before_today, "BOS", "DEN", "playin"),
        # Regular season (eligible) - various dates
        _game("002262600001", before, "DEN", "LAL", "regular"),
        _game("002262600002", day_before_today, "BOS", "DEN", "regular"),
        _game("002262600003", today, "GSW", "LAL", "regular"),
        _game("002262600004", after_today, "BOS", "GSW", "regular"),
        # Cup final (eligible)
        _game("006262600001", before, "DEN", "BOS", "cup_final"),
        _game("006262600002", day_before_today, "LAL", "DEN", "cup_final"),
    ]

    repo = FakeRepo(games=games)
    count = run(repo, season="2026-27", today=today, now=NOW)

    # Only eligible games from dates < today should be written
    written_dates = {n["date"] for n in repo.nights}
    # before and day_before_today should have nights
    assert before.isoformat() in written_dates
    assert day_before_today.isoformat() in written_dates
    # today and after_today should NOT have nights
    assert today.isoformat() not in written_dates
    assert after_today.isoformat() not in written_dates

    # Count should equal number of nights written
    assert count == len(repo.nights)
    assert count == 2  # one night for "before", one for "day_before_today"


def test_rebuild_nights_preserves_existing_rows():
    """Aucune suppression : les soirées existantes en base doivent survivre."""
    before = date(2026, 10, 28)
    day_before_today = date(2026, 11, 1)
    future = date(2026, 12, 1)  # >= today, should not be touched

    # Pre-seed the repo with some nights
    # One for a date that will have new games (should be overwritten)
    # One for a date that will NOT have any eligible game (should survive, proving no delete)
    # One for a future date (should survive, proving no delete)
    existing_nights = [
        {
            "date": before.isoformat(),
            "season": "2026-27",
            "mode": "regular",
            "n_eligible_games": 1,
            "closing_at": "2026-10-29T00:00:00+02:00",
            "is_phantom": False,
        },
        {
            "date": date(2026, 10, 30).isoformat(),
            "season": "2026-27",
            "mode": "regular",
            "n_eligible_games": 0,
            "closing_at": "2026-10-31T00:00:00+02:00",
            "is_phantom": True,  # No eligible games this day
        },
        {
            "date": future.isoformat(),
            "season": "2026-27",
            "mode": "regular",
            "n_eligible_games": 1,
            "closing_at": "2026-12-02T00:00:00+02:00",
            "is_phantom": False,
        },
    ]

    games = [
        # Add a game for "before" (should update the existing night)
        _game("002262600001", before, "DEN", "LAL", "regular"),
        # Add a game for day_before_today
        _game("002262600002", day_before_today, "BOS", "DEN", "regular"),
        # No games for the phantom-night date (should survive)
        # No games for future date (should survive)
    ]

    repo = FakeRepo(games=games, series=[])
    # Add pre-existing nights
    repo.nights = list(existing_nights)

    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    # The phantom night (no eligible games) should survive
    phantom_date = date(2026, 10, 30).isoformat()
    assert any(n["date"] == phantom_date for n in repo.nights), "Phantom night should survive"

    # The future night should survive
    assert any(n["date"] == future.isoformat() for n in repo.nights), "Future night should survive"

    # Count should only include new nights written (before, day_before_today)
    assert count == 2


def test_rebuild_nights_row_format():
    """Vérifie le format des lignes écrites (closing_at, updated_at, etc.)."""
    d = date(2026, 10, 28)
    games = [
        _game("002262600001", d, "DEN", "LAL", "regular", tip_off="2026-10-28T02:30:00Z"),
    ]

    repo = FakeRepo(games=games)
    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    assert count == 1
    night = repo.nights[0]

    # Check required fields
    assert set(night.keys()) >= {"date", "season", "mode", "n_eligible_games", "closing_at", "is_phantom", "updated_at"}
    # Check values
    assert night["date"] == d.isoformat()
    assert night["season"] == "2026-27"
    assert night["mode"] == "regular"
    assert night["n_eligible_games"] == 1
    assert night["is_phantom"] is False
    assert night["updated_at"] == NOW.isoformat()
    # closing_at should be a valid ISO string
    assert isinstance(night["closing_at"], str)
    datetime.fromisoformat(night["closing_at"])  # Should not raise


def test_rebuild_nights_tip_off_none_uses_midnight():
    """Sans tip_off, closing_at doit être minuit à Paris du lendemain."""
    d = date(2026, 10, 28)
    games = [
        _game("002262600001", d, "DEN", "LAL", "regular", tip_off=None),
    ]

    repo = FakeRepo(games=games)
    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    assert count == 1
    night = repo.nights[0]

    # closing_at should be midnight Paris time of the next day
    closing = datetime.fromisoformat(night["closing_at"])
    # It should be the midnight of 2026-10-29
    assert closing.date() == date(2026, 10, 29)
    assert closing.hour == 0 and closing.minute == 0


def test_rebuild_nights_regular_and_cup_final_eligible():
    """Regular et Cup final sont tous deux écrites."""
    d = date(2026, 10, 28)
    games = [
        _game("002262600001", d, "DEN", "LAL", "regular"),
        _game("006262600001", d, "BOS", "DEN", "cup_final"),
    ]

    repo = FakeRepo(games=games)
    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    # Both should be in the same night
    assert count == 1
    night = repo.nights[0]
    assert night["n_eligible_games"] == 2


def test_rebuild_nights_playoffs_eligible():
    """Les matchs de playoffs sont aussi écrites."""
    d = date(2026, 10, 28)
    games = [
        _game("004262600001", d, "DEN", "LAL", "playoffs"),
    ]

    repo = FakeRepo(games=games)
    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    assert count == 1
    night = repo.nights[0]
    assert night["n_eligible_games"] == 1
    assert night["mode"] == "playoffs"  # mode should be "playoffs" for playoff games


def test_rebuild_nights_phantom_games():
    """Les soirées avec seulement des matchs fantômes ont is_phantom=True, n_eligible_games=0."""
    d = date(2026, 10, 28)
    # Scheduled playoff game in a completed series (phantom)
    series = [{"id": "s1", "season": "2026-27", "status": "completed", "home_team": "DEN", "away_team": "LAL"}]
    games = [
        _game("004262600001", d, "DEN", "LAL", "playoffs", status="scheduled", season="2026-27"),
    ]

    repo = FakeRepo(games=games, series=series)
    count = run(repo, season="2026-27", today=TODAY, now=NOW)

    assert count == 1
    night = repo.nights[0]
    assert night["is_phantom"] is True
    assert night["n_eligible_games"] == 0
