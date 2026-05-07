"""Seed the team_outlook + player_team_rank tables from the user's
handwritten Round 2 grid (2026-05-07 conversation).

Re-run idempotently: upserts on team / player_id keys. Edit the
GRID/OUTLOOKS dicts when the user revises his bracket view.
"""
from sync.db import get_client


# Per-team strategic stance.
#   advance   = expected to go deep, save the top picks
#   eliminate = expected to bow out this round, burn down the list
#   tossup    = balanced series, mid-list bias
OUTLOOKS = {
    "OKC": {"outlook": "advance", "home_save_top": True,
            "notes": "User reserves SGA + Chet for finals."},
    "NYK": {"outlook": "advance", "home_save_top": True,
            "notes": "Favori vs PHI."},
    "SAS": {"outlook": "advance", "home_save_top": True,
            "notes": "Favori vs MIN, prudence."},
    "PHI": {"outlook": "advance", "home_save_top": True,
            "notes": "Pool réduit (Embiid + Maxey déjà brûlés), prudence."},
    "DET": {"outlook": "tossup", "home_save_top": False,
            "notes": "Série équilibrée vs CLE; pool DET déjà mince."},
    "CLE": {"outlook": "tossup", "home_save_top": False,
            "notes": "Série équilibrée vs DET; pick milieu de liste."},
    "LAL": {"outlook": "eliminate", "home_save_top": True,
            "notes": "Probable sortie ce tour; garder top picks pour les home games."},
    "MIN": {"outlook": "eliminate", "home_save_top": True,
            "notes": "SAS favori; prudence avec milieu de liste prioritaire."},
}

# Per-team save ranks. (player_name, save_rank). Lower rank = saved
# longer, higher rank = burned earlier.
GRID = {
    "LAL": [
        ("Austin Reaves", 1),
        ("Luka Dončić", 2),
        ("Rui Hachimura", 3),
        ("Deandre Ayton", 4),
        ("Marcus Smart", 5),
    ],
    "DET": [
        ("Ausar Thompson", 1),
        ("Jalen Duren", 2),
    ],
    "PHI": [
        ("VJ Edgecombe", 1),
        ("Paul George", 2),
        ("Kelly Oubre Jr.", 3),
    ],
    "OKC": [
        ("Shai Gilgeous-Alexander", 1),
        ("Chet Holmgren", 2),
        ("Jalen Williams", 3),
        ("Ajay Mitchell", 4),
        ("Alex Caruso", 5),
        ("Jaylin Williams", 6),
    ],
    "NYK": [
        ("Jalen Brunson", 1),
        ("Karl-Anthony Towns", 2),
        ("Mikal Bridges", 3),
        ("Josh Hart", 4),
    ],
    "MIN": [
        ("Jaden McDaniels", 1),
        ("Anthony Edwards", 2),
        ("Naz Reid", 3),
        ("Julius Randle", 4),
        ("Terrence Shannon Jr.", 5),
    ],
    "CLE": [
        ("Donovan Mitchell", 1),
        ("James Harden", 2),
        ("Jarrett Allen", 3),
        ("Max Strus", 4),
    ],
    "SAS": [
        ("Victor Wembanyama", 1),
        ("Devin Vassell", 2),
        ("Dylan Harper", 3),
        ("De'Aaron Fox", 4),
        ("Julian Champagnie", 5),
        ("Keldon Johnson", 6),
    ],
}


def seed() -> None:
    sb = get_client()

    # 1. Outlooks
    rows = [
        {"team": team, **payload} for team, payload in OUTLOOKS.items()
    ]
    sb.table("team_outlook").upsert(rows, on_conflict="team").execute()
    print(f"  team_outlook: {len(rows)} rows upserted")

    # 2. Player ranks. Resolve names to ids team-by-team to avoid name
    # collisions (e.g. "Jalen Williams" exists on multiple rosters in
    # league history).
    upserts = []
    missing: list[tuple[str, str]] = []
    for team, entries in GRID.items():
        team_players = (
            sb.table("players").select("id, name").eq("team", team).execute().data or []
        )
        by_name = {p["name"]: p["id"] for p in team_players}
        # Loose match for accents / Jr. suffixes that may differ between
        # the grid spelling and what nba_api returned.
        for grid_name, rank in entries:
            pid = by_name.get(grid_name)
            if pid is None:
                pid = next(
                    (p["id"] for p in team_players
                     if _normalize(p["name"]) == _normalize(grid_name)),
                    None,
                )
            if pid is None:
                missing.append((team, grid_name))
                continue
            upserts.append({
                "player_id": pid, "team": team, "save_rank": rank,
            })
    if upserts:
        sb.table("player_team_rank").upsert(
            upserts, on_conflict="player_id"
        ).execute()
    print(f"  player_team_rank: {len(upserts)} rows upserted")
    if missing:
        print(f"  ⚠ {len(missing)} players not matched by name:")
        for team, name in missing:
            print(f"      {team:<4} {name}")


def _normalize(name: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.lower().replace(".", "").replace("'", "").strip()


if __name__ == "__main__":
    seed()
