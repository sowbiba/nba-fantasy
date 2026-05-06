"""Per-team defender matchup report.

For each player of a given team, prints the primary and secondary
defender on him from the opposing team during the current series
window, the share of matchup time, and an offensive efficiency
indicator (TTFL offensif alloué par 36 min de matchup vs son
TTFL/36 saison).

Reads the `matchup_aggregates` rows that the daily sync already
produces (sync.matchups). Source data comes from BoxScoreMatchupsV3,
restricted by `opponent_team`. Note: regular-season meetings against
the same opponent share the same row (series_id null) — for a clean
playoff-only view, run after sync has tagged a series_id, or filter
by `last_game_id` to a known playoff game.

Usage:
    python -m sync.matchup_report MIN SAS
    python -m sync.matchup_report SAS MIN
"""
import sys

from sync.db import get_client


def report(team: str, opponent: str) -> None:
    sb = get_client()
    players = (
        sb.table("players")
        .select("id, name, avg_ttfl_season, avg_minutes_l10")
        .eq("team", team)
        .execute()
        .data
    )
    pmap = {p["id"]: p for p in players}
    rows = (
        sb.table("matchup_aggregates")
        .select("*")
        .eq("opponent_team", opponent)
        .in_("player_id", list(pmap.keys()))
        .execute()
        .data
    )
    rows.sort(key=lambda r: -float(r["matchup_minutes_total"] or 0))

    header = (
        f"{team} vs {opponent} — defender matchups "
        f"({len(rows)} joueurs avec données)\n"
    )
    print(header)
    print(
        f"{'Joueur':<24}{'1er défenseur':<22}{'min':>5}{'%':>5}   "
        f"{'2e défenseur':<22}{'min':>5}{'%':>5}   "
        f"{'TTFLoff/36':>10}{'TTFL/36 saison':>15}{'samples':>8}"
    )
    print("-" * 130)
    for r in rows:
        p = pmap.get(r["player_id"], {})
        name = p.get("name", "?")
        season = float(p.get("avg_ttfl_season") or 0)
        mpg = float(p.get("avg_minutes_l10") or 0)
        season_per36 = round(season / mpg * 36, 1) if mpg else 0.0
        total = float(r["matchup_minutes_total"])
        p1_min = round(total * float(r["primary_def_share"]), 2)
        p2_min = round(total * float(r["secondary_def_share"]), 2)
        p1pct = int(round(float(r["primary_def_share"]) * 100))
        p2pct = int(round(float(r["secondary_def_share"]) * 100))
        print(
            f"{name:<24}{(r['primary_def_name'] or '-'):<22}{p1_min:>5}{p1pct:>4}%   "
            f"{(r['secondary_def_name'] or '-'):<22}{p2_min:>5}{p2pct:>4}%   "
            f"{float(r['allowed_off_ttfl_per36']):>10}{season_per36:>15}{r['samples_count']:>8}"
        )


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python -m sync.matchup_report <TEAM> <OPPONENT>", file=sys.stderr)
        sys.exit(2)
    report(sys.argv[1].upper(), sys.argv[2].upper())


if __name__ == "__main__":
    main()
