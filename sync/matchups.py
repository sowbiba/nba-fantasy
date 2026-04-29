"""Per-pair matchup aggregation.

Reads BoxScoreMatchupsV3 rows from a single game, identifies each
offensive player's primary defender(s), synthesizes a per-36 "offensive
TTFL" the player produced while that defender was on him, and upserts
the result into the `matchup_aggregates` table keyed on
(player_id, opponent_team, series_id).

Why "offensive only": the matchup endpoint reports stats *while a given
defender was the primary*, but rebounds, steals, and the player's own
blocks aren't matchup-attributable in any meaningful way. We synthesize
only PTS + AST + FGM + 3PM + FTM − TOV − missed shots — the same
formula as full TTFL minus REB/STL/BLK_BY — and the scoring layer
compares this to the equivalent fraction of the player's season
average. That gives a clean defender-specific suppression factor.
"""
from collections import defaultdict
from datetime import UTC, datetime

from sync.fetcher import fetch_box_score_matchups


# Confidence threshold below which we don't bother updating the row —
# 5 minutes of total matchup data is too thin to influence anything.
MIN_MATCHUP_SECONDS = 60


def _offensive_ttfl(
    pts: int, ast: int, tov: int,
    fgm: int, fga: int, tpm: int, tpa: int, ftm: int, fta: int,
) -> float:
    """TTFL minus REB/STL/BLK_BY (not matchup-attributable)."""
    positive = pts + ast + fgm + tpm + ftm
    negative = tov + (fga - fgm) + (tpa - tpm) + (fta - ftm)
    return float(positive - negative)


def _aggregate_rows(rows: list[dict]) -> dict:
    """Group raw V3 rows by offensive player.

    Returns: {off_player_id: {
        "off_team": str, "name": str,
        "by_def": {def_id: {<sums>}},
        "totals": {<sums across all defenders>},
    }}
    """
    by_off: dict[int, dict] = {}
    for r in rows:
        opid = r["off_player_id"]
        slot = by_off.setdefault(opid, {
            "off_team": r["off_team"],
            "off_name": r["off_player_name"],
            "by_def": defaultdict(lambda: {
                "def_name": "",
                "seconds": 0.0,
                "pts": 0, "ast": 0, "tov": 0, "blocks": 0,
                "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0,
            }),
            "totals": {
                "seconds": 0.0,
                "pts": 0, "ast": 0, "tov": 0, "blocks": 0,
                "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0,
            },
        })
        d = slot["by_def"][r["def_player_id"]]
        d["def_name"] = r["def_player_name"]
        d["seconds"] += r["matchup_seconds"]
        d["pts"] += r["player_points"]
        d["ast"] += r["matchup_assists"]
        d["tov"] += r["matchup_turnovers"]
        d["blocks"] += r["matchup_blocks"]
        d["fgm"] += r["matchup_fgm"]
        d["fga"] += r["matchup_fga"]
        d["tpm"] += r["matchup_tpm"]
        d["tpa"] += r["matchup_tpa"]
        d["ftm"] += r["matchup_ftm"]
        d["fta"] += r["matchup_fta"]

        t = slot["totals"]
        t["seconds"] += r["matchup_seconds"]
        t["pts"] += r["player_points"]
        t["ast"] += r["matchup_assists"]
        t["tov"] += r["matchup_turnovers"]
        t["blocks"] += r["matchup_blocks"]
        t["fgm"] += r["matchup_fgm"]
        t["fga"] += r["matchup_fga"]
        t["tpm"] += r["matchup_tpm"]
        t["tpa"] += r["matchup_tpa"]
        t["ftm"] += r["matchup_ftm"]
        t["fta"] += r["matchup_fta"]
    return by_off


def _build_aggregate_payload(
    player_id: int,
    off_team: str,
    opponent_team: str,
    series_id: int | None,
    by_off_slot: dict,
    last_game_id: str,
) -> dict | None:
    """Turn one player's aggregated rows into a `matchup_aggregates` row."""
    by_def = by_off_slot["by_def"]
    if not by_def:
        return None

    # Rank defenders by matchup minutes (top first).
    ranked = sorted(by_def.items(), key=lambda kv: kv[1]["seconds"], reverse=True)
    primary_def_id, primary = ranked[0]
    secondary_def_id, secondary = (ranked[1] if len(ranked) > 1 else (None, None))

    totals = by_off_slot["totals"]
    total_seconds = totals["seconds"]
    if total_seconds < MIN_MATCHUP_SECONDS:
        return None

    primary_minutes = primary["seconds"] / 60.0
    if primary_minutes <= 0:
        return None

    # Synthesize "offensive TTFL" produced while the primary defender
    # was on this player, normalized per 36 matchup minutes.
    off_ttfl = _offensive_ttfl(
        primary["pts"], primary["ast"], primary["tov"],
        primary["fgm"], primary["fga"],
        primary["tpm"], primary["tpa"],
        primary["ftm"], primary["fta"],
    )
    factor = 36.0 / primary_minutes
    allowed_off_ttfl_per36 = off_ttfl * factor

    fg_pct = primary["fgm"] / primary["fga"] if primary["fga"] else 0.0
    tp_pct = primary["tpm"] / primary["tpa"] if primary["tpa"] else 0.0

    return {
        "player_id": int(player_id),
        "opponent_team": opponent_team,
        "series_id": int(series_id) if series_id is not None else None,
        "primary_def_id": int(primary_def_id),
        "primary_def_name": primary["def_name"],
        "primary_def_share": (
            primary["seconds"] / total_seconds if total_seconds else 0.0
        ),
        "secondary_def_id": int(secondary_def_id) if secondary_def_id else None,
        "secondary_def_name": secondary["def_name"] if secondary else None,
        "secondary_def_share": (
            secondary["seconds"] / total_seconds
            if (secondary and total_seconds) else 0.0
        ),
        "allowed_off_ttfl_per36": round(allowed_off_ttfl_per36, 2),
        "allowed_pts_per36": round(primary["pts"] * factor, 2),
        "allowed_ast_per36": round(primary["ast"] * factor, 2),
        "allowed_to_per36": round(primary["tov"] * factor, 2),
        "allowed_blk_against": int(primary["blocks"]),
        "allowed_fg_pct": round(fg_pct, 3),
        "allowed_3p_pct": round(tp_pct, 3),
        "matchup_minutes_total": round(total_seconds / 60.0, 2),
        "primary_def_minutes": round(primary_minutes, 2),
        "samples_count": 1,  # incremented on conflict by the upsert helper
        "last_game_id": last_game_id,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def lookup_pair_matchup(
    client, player_id: int, opponent_team: str
) -> tuple[float | None, float]:
    """Return (allowed_off_ttfl_per36, primary_def_minutes) for the active
    in-series aggregate, or (None, 0.0) if there's no usable sample.

    Picks the row with the most accumulated primary-defender minutes
    (highest confidence) when several series-bound rows exist.
    """
    rows = (
        client.table("matchup_aggregates")
        .select(
            "allowed_off_ttfl_per36, primary_def_minutes, series_id, "
            "matchup_minutes_total"
        )
        .eq("player_id", player_id)
        .eq("opponent_team", opponent_team)
        .order("primary_def_minutes", desc=True)
        .limit(5)
        .execute()
        .data
    ) or []

    if not rows:
        return None, 0.0

    # Prefer the most-minutes row that has any usable signal at all.
    for r in rows:
        minutes = float(r.get("primary_def_minutes") or 0)
        rate = r.get("allowed_off_ttfl_per36")
        if minutes > 0 and rate is not None:
            return float(rate), minutes
    return None, 0.0


def update_aggregates_for_game(
    client,
    game_id: str,
    home_team: str,
    away_team: str,
    series_id: int | None,
) -> int:
    """Pull matchup data for one game and merge it into matchup_aggregates.

    Idempotent: re-running on the same game_id won't double-count
    (samples are merged via game_id check). Returns the number of
    (player, opponent) rows touched.
    """
    rows = fetch_box_score_matchups(game_id)
    if not rows:
        return 0

    by_off = _aggregate_rows(rows)
    touched = 0

    for off_id, slot in by_off.items():
        # Opponent is the team the defender plays for. We don't have it
        # directly, but the offensive player belongs to one of the two
        # teams in this game; the opponent is the other.
        opponent = away_team if slot["off_team"] == home_team else home_team

        payload = _build_aggregate_payload(
            player_id=off_id,
            off_team=slot["off_team"],
            opponent_team=opponent,
            series_id=series_id,
            by_off_slot=slot,
            last_game_id=game_id,
        )
        if payload is None:
            continue

        # Read the existing aggregate (if any) and merge by averaging the
        # per-36 rates weighted by primary_def_minutes. Skip the merge
        # entirely when the row already references this game_id (re-run
        # safety).
        existing_q = (
            client.table("matchup_aggregates")
            .select("*")
            .eq("player_id", payload["player_id"])
            .eq("opponent_team", payload["opponent_team"])
        )
        if payload["series_id"] is None:
            existing_q = existing_q.is_("series_id", "null")
        else:
            existing_q = existing_q.eq("series_id", payload["series_id"])
        existing = existing_q.execute().data

        if existing:
            row = existing[0]
            if row.get("last_game_id") == game_id:
                # Already counted this game — nothing to do.
                continue
            old_min = float(row.get("primary_def_minutes") or 0)
            new_min = payload["primary_def_minutes"]
            total_min = old_min + new_min
            if total_min <= 0:
                continue

            def blend(old_key, new_key):
                return (
                    (float(row.get(old_key) or 0) * old_min)
                    + (payload[new_key] * new_min)
                ) / total_min

            payload["allowed_off_ttfl_per36"] = round(
                blend("allowed_off_ttfl_per36", "allowed_off_ttfl_per36"), 2
            )
            payload["allowed_pts_per36"] = round(
                blend("allowed_pts_per36", "allowed_pts_per36"), 2
            )
            payload["allowed_ast_per36"] = round(
                blend("allowed_ast_per36", "allowed_ast_per36"), 2
            )
            payload["allowed_to_per36"] = round(
                blend("allowed_to_per36", "allowed_to_per36"), 2
            )
            payload["allowed_fg_pct"] = round(
                blend("allowed_fg_pct", "allowed_fg_pct"), 3
            )
            payload["allowed_3p_pct"] = round(
                blend("allowed_3p_pct", "allowed_3p_pct"), 3
            )
            payload["matchup_minutes_total"] = round(
                float(row.get("matchup_minutes_total") or 0)
                + payload["matchup_minutes_total"],
                2,
            )
            payload["primary_def_minutes"] = round(total_min, 2)
            payload["allowed_blk_against"] = (
                int(row.get("allowed_blk_against") or 0)
                + payload["allowed_blk_against"]
            )
            payload["samples_count"] = (
                int(row.get("samples_count") or 0) + 1
            )
            client.table("matchup_aggregates").update(payload).eq(
                "id", row["id"]
            ).execute()
        else:
            client.table("matchup_aggregates").insert(payload).execute()

        touched += 1

    return touched
