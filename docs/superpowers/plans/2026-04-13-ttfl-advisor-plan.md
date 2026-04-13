# TTFL Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a TTFL pick advisor that recommends the top 3 NBA players to pick each game night, with argumentaire and playoff strategy, accessible as a PWA from anywhere.

**Architecture:** Python cron (local machine) fetches NBA data from cdn.nba.com/nba_api + ESPN injuries, computes scores with a 6-factor engine + playoff strategy layer, pushes results to Supabase. Next.js PWA on Vercel reads Supabase and displays recommendations, picks history, and strategic view.

**Tech Stack:** Python 3.12+ (nba_api, httpx, supabase-py, numpy) / Next.js 15 (App Router, TypeScript, Tailwind CSS, @supabase/supabase-js) / Supabase (PostgreSQL) / Vercel

---

## File Structure

```
nba-fantasy/
├── sync/                          # Python backend
│   ├── __init__.py
│   ├── config.py                  # Env vars, constants
│   ├── ttfl.py                    # TTFL score calculator (pure function)
│   ├── fetcher.py                 # NBA data fetcher (nba_api + cdn.nba.com)
│   ├── injuries.py                # ESPN injury fetcher
│   ├── db.py                      # Supabase read/write layer
│   ├── scoring.py                 # 6-factor scoring engine
│   ├── strategy.py                # Playoff strategy layer
│   ├── advisor.py                 # Argumentaire generator (pros/cons/verdict)
│   └── main.py                    # Cron orchestrator
├── tests/
│   ├── __init__.py
│   ├── test_ttfl.py
│   ├── test_scoring.py
│   ├── test_strategy.py
│   └── test_advisor.py
├── web/                           # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx         # Root layout + bottom nav
│   │   │   ├── page.tsx           # Tonight (home)
│   │   │   ├── player/
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx   # Player detail + verdict
│   │   │   ├── picks/
│   │   │   │   └── page.tsx       # My picks history
│   │   │   └── strategy/
│   │   │       └── page.tsx       # Strategy dashboard
│   │   ├── lib/
│   │   │   └── supabase.ts        # Supabase client singleton
│   │   ├── components/
│   │   │   ├── BottomNav.tsx
│   │   │   ├── SyncStatus.tsx
│   │   │   ├── GamesCollapsible.tsx
│   │   │   ├── StrategyBanner.tsx
│   │   │   ├── RecommendationCard.tsx
│   │   │   ├── PlayerList.tsx
│   │   │   └── ProsCons.tsx
│   │   └── types/
│   │       └── index.ts           # Shared TypeScript types
│   ├── public/
│   │   ├── manifest.json
│   │   └── icons/                 # PWA icons
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── supabase/
│   └── schema.sql                 # Full DB schema
├── requirements.txt               # Python dependencies
├── .env.example                   # Env template
└── .gitignore
```

---

## Task 1: Project Setup + Supabase Schema

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `supabase/schema.sql`
- Create: `sync/__init__.py`
- Create: `sync/config.py`
- Create: `tests/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create Python dependencies**

```
# requirements.txt
nba_api>=1.5
httpx>=0.27
supabase>=2.0
numpy>=1.26
python-dotenv>=1.0
schedule>=1.2
```

- [ ] **Step 2: Create env template**

```
# .env.example
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
```

- [ ] **Step 3: Update .gitignore**

Append to existing `.gitignore`:

```
# Python
__pycache__/
*.pyc
venv/
.env

# Node
web/node_modules/
web/.next/
web/out/

# IDE
.vscode/
.idea/
```

- [ ] **Step 4: Create Supabase schema**

```sql
-- supabase/schema.sql

-- Players with aggregated stats
create table players (
  id integer primary key,
  name text not null,
  team text not null,
  position text not null,
  injury_status text,
  injury_detail text,
  avg_ttfl_l5 numeric default 0,
  avg_ttfl_l10 numeric default 0,
  avg_ttfl_l20 numeric default 0,
  avg_ttfl_season numeric default 0,
  stddev_ttfl numeric default 0,
  home_avg numeric default 0,
  away_avg numeric default 0,
  usage_rate numeric default 0,
  updated_at timestamptz default now()
);

-- Playoff series (must be created before games which references it)
create table series (
  id serial primary key,
  round integer not null,
  home_team text not null,
  away_team text not null,
  home_wins integer default 0,
  away_wins integer default 0,
  status text not null default 'active'
);

-- Games schedule
create table games (
  id text primary key,
  date date not null,
  home_team text not null,
  away_team text not null,
  tip_off timestamptz,
  series_id integer references series(id),
  game_number integer,
  status text not null default 'scheduled'
);

-- Individual game box scores
create table game_logs (
  id serial primary key,
  player_id integer not null references players(id),
  game_id text not null references games(id),
  date date not null,
  pts integer default 0,
  reb integer default 0,
  ast integer default 0,
  stl integer default 0,
  blk integer default 0,
  fgm integer default 0,
  fga integer default 0,
  tpm integer default 0,
  tpa integer default 0,
  ftm integer default 0,
  fta integer default 0,
  tov integer default 0,
  minutes integer default 0,
  ttfl_score integer default 0,
  is_home boolean default false,
  unique(player_id, game_id)
);

-- Daily recommendations (top 50)
create table recommendations (
  id serial primary key,
  date date not null,
  player_id integer not null references players(id),
  rank integer not null,
  estimated_score numeric not null,
  perf_score numeric default 0,
  matchup_score numeric default 0,
  strategy_score numeric,
  pros jsonb default '[]',
  cons jsonb default '[]',
  verdict text default '',
  tier text not null,
  tags jsonb default '[]',
  computed_at timestamptz default now(),
  unique(date, player_id)
);

-- User picks
create table picks (
  id serial primary key,
  player_id integer not null references players(id),
  game_id text not null references games(id),
  date date not null,
  mode text not null default 'playoffs',
  estimated_score numeric,
  actual_score integer,
  picked_at timestamptz default now(),
  unique(date)
);

-- Team defensive stats
create table team_defense (
  team text primary key,
  vs_guards_ttfl_avg numeric default 0,
  vs_forwards_ttfl_avg numeric default 0,
  vs_centers_ttfl_avg numeric default 0,
  def_rating numeric default 0,
  updated_at timestamptz default now()
);

-- Sync log
create table sync_log (
  id serial primary key,
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text not null default 'running',
  players_updated integer default 0,
  error_message text
);

-- Indexes for frequent queries
create index idx_recommendations_date on recommendations(date);
create index idx_game_logs_player_date on game_logs(player_id, date desc);
create index idx_games_date on games(date);
create index idx_picks_mode on picks(mode);

-- Enable RLS but allow anon read access
alter table players enable row level security;
alter table games enable row level security;
alter table series enable row level security;
alter table game_logs enable row level security;
alter table recommendations enable row level security;
alter table picks enable row level security;
alter table team_defense enable row level security;
alter table sync_log enable row level security;

-- Read-only policies for anon (frontend)
create policy "anon read players" on players for select using (true);
create policy "anon read games" on games for select using (true);
create policy "anon read series" on series for select using (true);
create policy "anon read game_logs" on game_logs for select using (true);
create policy "anon read recommendations" on recommendations for select using (true);
create policy "anon read picks" on picks for select using (true);
create policy "anon read team_defense" on team_defense for select using (true);
create policy "anon read sync_log" on sync_log for select using (true);

-- Write policies for service role (Python backend)
create policy "service write players" on players for all using (true) with check (true);
create policy "service write games" on games for all using (true) with check (true);
create policy "service write series" on series for all using (true) with check (true);
create policy "service write game_logs" on game_logs for all using (true) with check (true);
create policy "service write recommendations" on recommendations for all using (true) with check (true);
create policy "service write picks" on picks for all using (true) with check (true);
create policy "service write team_defense" on team_defense for all using (true) with check (true);
create policy "service write sync_log" on sync_log for all using (true) with check (true);
```

**Note:** The `series` table is created before `games` because `games.series_id` references it.

- [ ] **Step 5: Create Python config module**

```python
# sync/__init__.py
```

```python
# sync/config.py
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ESPN injury endpoint template
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# NBA API request delay (avoid rate limiting)
NBA_API_DELAY = 0.6  # seconds between requests

# Scoring weights
WEIGHTS = {
    "weighted_avg": 0.35,
    "matchup": 0.25,
    "home_away": 0.10,
    "fatigue": 0.10,
    "trend": 0.10,
    "consistency": 0.10,
}

# Fatigue modifiers
FATIGUE = {
    "b2b": -0.08,
    "3_in_4": -0.12,
    "rest_3plus": 0.03,
}

# Injury modifiers on estimated score
INJURY_MODIFIER = {
    "Questionable": -0.15,
    "Day-To-Day": -0.10,
}

# Playoff strategy: burn threshold
# If best future spot > tonight + 10%, recommend saving
BURN_THRESHOLD = 0.10
```

```python
# tests/__init__.py
```

- [ ] **Step 6: Install Python dependencies and verify**

Run: `cd /home/isow/workspace/perso/nba-fantasy && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
Expected: All packages install successfully.

Run: `python -c "from nba_api.stats.endpoints import PlayerGameLog; print('nba_api OK')"`
Expected: `nba_api OK`

- [ ] **Step 7: Set up Supabase project**

Manual step for the user:
1. Go to https://supabase.com and create a new project
2. Copy the SQL from `supabase/schema.sql` into the SQL Editor and run it
3. Copy the project URL and anon key from Settings > API
4. Create `.env` from `.env.example` and fill in the values
5. Get the service role key from Settings > API > service_role (secret) and add to `.env`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore supabase/schema.sql sync/__init__.py sync/config.py tests/__init__.py
git commit -m "feat: project setup with Supabase schema and Python config"
```

---

## Task 2: TTFL Score Calculator

**Files:**
- Create: `sync/ttfl.py`
- Create: `tests/test_ttfl.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ttfl.py
from sync.ttfl import compute_ttfl_score


def test_ttfl_score_basic():
    """Standard stat line: 30pts, 10reb, 8ast, 1stl, 2blk, 11/20fg, 3/7 3pt, 5/6ft, 3to"""
    score = compute_ttfl_score(
        pts=30, reb=10, ast=8, stl=1, blk=2,
        fgm=11, fga=20, tpm=3, tpa=7, ftm=5, fta=6, tov=3,
    )
    # Positive: 30+10+8+1+2+11+3+5 = 70
    # Negative: 3+9+4+1 = 17
    # TTFL = 70 - 17 = 53
    assert score == 53


def test_ttfl_score_monster_game():
    """Triple-double efficient game"""
    score = compute_ttfl_score(
        pts=45, reb=15, ast=12, stl=3, blk=1,
        fgm=18, fga=25, tpm=5, tpa=8, ftm=4, fta=4, tov=2,
    )
    # Positive: 45+15+12+3+1+18+5+4 = 103
    # Negative: 2+7+3+0 = 12
    # TTFL = 103 - 12 = 91
    assert score == 91


def test_ttfl_score_bad_game():
    """Inefficient low-scoring game"""
    score = compute_ttfl_score(
        pts=8, reb=2, ast=1, stl=0, blk=0,
        fgm=3, fga=12, tpm=1, tpa=6, ftm=1, fta=2, tov=4,
    )
    # Positive: 8+2+1+0+0+3+1+1 = 16
    # Negative: 4+9+5+1 = 19
    # TTFL = 16 - 19 = -3
    assert score == -3


def test_ttfl_score_zero_stats():
    """DNP or all zeros"""
    score = compute_ttfl_score(
        pts=0, reb=0, ast=0, stl=0, blk=0,
        fgm=0, fga=0, tpm=0, tpa=0, ftm=0, fta=0, tov=0,
    )
    assert score == 0


def test_compute_ttfl_from_game_log():
    """Test dict-based input matching nba_api game log format"""
    from sync.ttfl import compute_ttfl_from_game_log

    game_log = {
        "PTS": 25, "REB": 7, "AST": 5, "STL": 2, "BLK": 1,
        "FGM": 10, "FGA": 18, "FG3M": 3, "FG3A": 7, "FTM": 2, "FTA": 3, "TOV": 2,
    }
    score = compute_ttfl_from_game_log(game_log)
    # Positive: 25+7+5+2+1+10+3+2 = 55
    # Negative: 2+8+4+1 = 15
    # TTFL = 55 - 15 = 40
    assert score == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/isow/workspace/perso/nba-fantasy && source venv/bin/activate && python -m pytest tests/test_ttfl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync.ttfl'`

- [ ] **Step 3: Write the implementation**

```python
# sync/ttfl.py
"""TTFL score calculator.

Formula: (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM)
       - (TOV + FG_miss + 3P_miss + FT_miss)
"""


def compute_ttfl_score(
    pts: int, reb: int, ast: int, stl: int, blk: int,
    fgm: int, fga: int, tpm: int, tpa: int, ftm: int, fta: int, tov: int,
) -> int:
    positive = pts + reb + ast + stl + blk + fgm + tpm + ftm
    negative = tov + (fga - fgm) + (tpa - tpm) + (fta - ftm)
    return positive - negative


def compute_ttfl_from_game_log(log: dict) -> int:
    """Compute TTFL score from an nba_api game log dict."""
    return compute_ttfl_score(
        pts=log["PTS"], reb=log["REB"], ast=log["AST"],
        stl=log["STL"], blk=log["BLK"],
        fgm=log["FGM"], fga=log["FGA"],
        tpm=log["FG3M"], tpa=log["FG3A"],
        ftm=log["FTM"], fta=log["FTA"],
        tov=log["TOV"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ttfl.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add sync/ttfl.py tests/test_ttfl.py
git commit -m "feat: TTFL score calculator with tests"
```

---

## Task 3: Supabase DB Layer

**Files:**
- Create: `sync/db.py`

- [ ] **Step 1: Write the Supabase client wrapper**

```python
# sync/db.py
"""Supabase read/write layer for the sync backend.

Uses the service_role key for full write access.
"""
from datetime import date, datetime
from supabase import create_client, Client
from sync.config import SUPABASE_URL, SUPABASE_SERVICE_KEY


def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# --- Sync log ---

def start_sync_log(client: Client) -> int:
    result = client.table("sync_log").insert({
        "started_at": datetime.utcnow().isoformat(),
        "status": "running",
    }).execute()
    return result.data[0]["id"]


def finish_sync_log(client: Client, log_id: int, players_updated: int):
    client.table("sync_log").update({
        "finished_at": datetime.utcnow().isoformat(),
        "status": "success",
        "players_updated": players_updated,
    }).eq("id", log_id).execute()


def fail_sync_log(client: Client, log_id: int, error: str):
    client.table("sync_log").update({
        "finished_at": datetime.utcnow().isoformat(),
        "status": "error",
        "error_message": error[:500],
    }).eq("id", log_id).execute()


# --- Players ---

def upsert_players(client: Client, players: list[dict]):
    """Upsert player rows. Each dict must have 'id' key."""
    if not players:
        return
    client.table("players").upsert(players, on_conflict="id").execute()


# --- Games ---

def upsert_games(client: Client, games: list[dict]):
    if not games:
        return
    client.table("games").upsert(games, on_conflict="id").execute()


# --- Series ---

def upsert_series(client: Client, series_list: list[dict]):
    if not series_list:
        return
    client.table("series").upsert(series_list, on_conflict="id").execute()


# --- Game logs ---

def upsert_game_logs(client: Client, logs: list[dict]):
    if not logs:
        return
    client.table("game_logs").upsert(
        logs, on_conflict="player_id,game_id"
    ).execute()


# --- Team defense ---

def upsert_team_defense(client: Client, defense: list[dict]):
    if not defense:
        return
    client.table("team_defense").upsert(defense, on_conflict="team").execute()


# --- Recommendations ---

def replace_recommendations(client: Client, recs: list[dict], target_date: date):
    """Delete existing recs for the date and insert new ones."""
    client.table("recommendations").delete().eq(
        "date", target_date.isoformat()
    ).execute()
    if recs:
        client.table("recommendations").insert(recs).execute()


# --- Picks ---

def get_picks(client: Client, mode: str = "playoffs") -> list[dict]:
    result = client.table("picks").select("*").eq("mode", mode).order("date", desc=True).execute()
    return result.data


def get_picked_player_ids(client: Client, mode: str = "playoffs") -> set[int]:
    picks = get_picks(client, mode)
    return {p["player_id"] for p in picks}


def insert_pick(client: Client, pick: dict):
    client.table("picks").insert(pick).execute()


def update_pick_actual_score(client: Client, pick_date: date, actual_score: int):
    client.table("picks").update({
        "actual_score": actual_score,
    }).eq("date", pick_date.isoformat()).execute()


# --- Read helpers (used by scoring) ---

def get_player_game_logs(client: Client, player_id: int, limit: int = 20) -> list[dict]:
    result = client.table("game_logs").select("*").eq(
        "player_id", player_id
    ).order("date", desc=True).limit(limit).execute()
    return result.data


def get_today_games(client: Client, today: date) -> list[dict]:
    result = client.table("games").select("*").eq("date", today.isoformat()).execute()
    return result.data


def get_active_series(client: Client) -> list[dict]:
    result = client.table("series").select("*").eq("status", "active").execute()
    return result.data


def get_team_defense(client: Client, team: str) -> dict | None:
    result = client.table("team_defense").select("*").eq("team", team).execute()
    return result.data[0] if result.data else None


def get_all_players(client: Client) -> list[dict]:
    result = client.table("players").select("*").execute()
    return result.data


def get_latest_sync(client: Client) -> dict | None:
    result = client.table("sync_log").select("*").order(
        "started_at", desc=True
    ).limit(1).execute()
    return result.data[0] if result.data else None
```

- [ ] **Step 2: Commit**

```bash
git add sync/db.py
git commit -m "feat: Supabase DB layer with read/write helpers"
```

---

## Task 4: NBA Data Fetcher

**Files:**
- Create: `sync/fetcher.py`

- [ ] **Step 1: Write the NBA data fetcher**

```python
# sync/fetcher.py
"""Fetch NBA data from cdn.nba.com and nba_api.

Collects: today's games, box scores, player game logs,
team rosters, team defense stats, playoff series.
"""
import time
from datetime import date, datetime, timedelta

from nba_api.stats.endpoints import (
    LeagueDashTeamStats,
    CommonTeamRoster,
    PlayerGameLog,
    ScoreboardV3,
)
from nba_api.live.nba.endpoints import BoxScore, ScoreBoard

from sync.config import NBA_API_DELAY
from sync.ttfl import compute_ttfl_score

import numpy as np


def fetch_today_scoreboard() -> dict:
    """Fetch today's scoreboard from nba_api live endpoint."""
    board = ScoreBoard()
    data = board.get_dict()
    return data["scoreboard"]


def parse_today_games(scoreboard: dict, today: date) -> list[dict]:
    """Parse scoreboard into game dicts for the games table."""
    games = []
    for game in scoreboard.get("games", []):
        game_id = game["gameId"]
        home = game["homeTeam"]["teamTricode"]
        away = game["awayTeam"]["teamTricode"]
        status_text = game.get("gameStatusText", "")
        tip_off_utc = game.get("gameTimeUTC")

        if game["gameStatus"] == 3:
            status = "final"
        elif game["gameStatus"] == 2:
            status = "live"
        else:
            status = "scheduled"

        games.append({
            "id": game_id,
            "date": today.isoformat(),
            "home_team": home,
            "away_team": away,
            "tip_off": tip_off_utc,
            "status": status,
        })
    return games


def fetch_live_box_score(game_id: str) -> list[dict]:
    """Fetch box score for a finished/live game. Returns player stat dicts."""
    try:
        box = BoxScore(game_id=game_id)
        data = box.get_dict()["game"]
    except Exception:
        return []

    players = []
    game_date = data.get("gameTimeUTC", "")[:10]

    for side in ["homeTeam", "awayTeam"]:
        team = data[side]
        team_tricode = team["teamTricode"]
        is_home = side == "homeTeam"

        for p in team.get("players", []):
            stats = p.get("statistics", {})
            if not stats or stats.get("minutes", "PT00M") == "PT00M":
                continue

            # Parse minutes from ISO duration "PT32M12.00S"
            min_str = stats.get("minutes", "PT0M")
            minutes = 0
            if "M" in min_str:
                try:
                    minutes = int(min_str.split("T")[1].split("M")[0])
                except (IndexError, ValueError):
                    pass

            pts = stats.get("points", 0)
            reb = stats.get("reboundsTotal", 0)
            ast = stats.get("assists", 0)
            stl = stats.get("steals", 0)
            blk = stats.get("blocks", 0)
            fgm = stats.get("fieldGoalsMade", 0)
            fga = stats.get("fieldGoalsAttempted", 0)
            tpm = stats.get("threePointersMade", 0)
            tpa = stats.get("threePointersAttempted", 0)
            ftm = stats.get("freeThrowsMade", 0)
            fta = stats.get("freeThrowsAttempted", 0)
            tov = stats.get("turnovers", 0)

            ttfl = compute_ttfl_score(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov)

            players.append({
                "player_id": p["personId"],
                "player_name": f"{p['firstName']} {p['familyName']}",
                "team": team_tricode,
                "game_id": data["gameId"],
                "date": game_date,
                "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
                "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa,
                "ftm": ftm, "fta": fta, "tov": tov,
                "minutes": minutes,
                "ttfl_score": ttfl,
                "is_home": is_home,
            })

    return players


def fetch_player_game_logs_nba_api(player_id: int, season: str = "2025-26") -> list[dict]:
    """Fetch game logs for a player via nba_api stats endpoint.
    Returns list of dicts with standard nba_api column names.
    """
    time.sleep(NBA_API_DELAY)
    try:
        log = PlayerGameLog(player_id=str(player_id), season=season)
        df = log.get_data_frames()[0]
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []


def fetch_team_rosters() -> dict[str, list[dict]]:
    """Fetch all NBA team rosters. Returns {tricode: [{player_id, name, position}, ...]}"""
    from nba_api.stats.static import teams as nba_teams

    rosters = {}
    for team in nba_teams.get_teams():
        time.sleep(NBA_API_DELAY)
        team_id = team["id"]
        tricode = team["abbreviation"]
        try:
            roster = CommonTeamRoster(team_id=str(team_id))
            df = roster.get_data_frames()[0]
            players = []
            for _, row in df.iterrows():
                pos = row.get("POSITION", "")
                # Normalize position to G/F/C
                if "Guard" in pos or pos in ("G", "G-F"):
                    pos_short = "G"
                elif "Forward" in pos or pos in ("F", "F-G", "F-C"):
                    pos_short = "F"
                elif "Center" in pos or pos == "C":
                    pos_short = "C"
                else:
                    pos_short = "F"  # default

                players.append({
                    "id": row["PLAYER_ID"],
                    "name": row["PLAYER"],
                    "team": tricode,
                    "position": pos_short,
                })
            rosters[tricode] = players
        except Exception:
            continue

    return rosters


def fetch_team_defense_stats(season: str = "2025-26") -> list[dict]:
    """Fetch league-wide team defense stats.
    Returns list of dicts with team defense metrics.
    """
    time.sleep(NBA_API_DELAY)
    try:
        stats = LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Opponent",
        )
        df = stats.get_data_frames()[0]
        results = []
        for _, row in df.iterrows():
            results.append({
                "team": row["TEAM_ABBREVIATION"],
                "def_rating": row.get("DEF_RATING", 0),
                # We'll compute per-position averages from game_logs in scoring.py
                "vs_guards_ttfl_avg": 0,
                "vs_forwards_ttfl_avg": 0,
                "vs_centers_ttfl_avg": 0,
            })
        return results
    except Exception:
        return []


def compute_player_aggregates(game_logs: list[dict]) -> dict:
    """Compute aggregated stats from a list of game log dicts (from game_logs table).

    Returns dict with: avg_ttfl_l5, avg_ttfl_l10, avg_ttfl_l20, avg_ttfl_season,
    stddev_ttfl, home_avg, away_avg.
    """
    if not game_logs:
        return {
            "avg_ttfl_l5": 0, "avg_ttfl_l10": 0, "avg_ttfl_l20": 0,
            "avg_ttfl_season": 0, "stddev_ttfl": 0, "home_avg": 0, "away_avg": 0,
        }

    scores = [g["ttfl_score"] for g in game_logs]
    home_scores = [g["ttfl_score"] for g in game_logs if g["is_home"]]
    away_scores = [g["ttfl_score"] for g in game_logs if not g["is_home"]]

    return {
        "avg_ttfl_l5": float(np.mean(scores[:5])) if len(scores) >= 1 else 0,
        "avg_ttfl_l10": float(np.mean(scores[:10])) if len(scores) >= 1 else 0,
        "avg_ttfl_l20": float(np.mean(scores[:20])) if len(scores) >= 1 else 0,
        "avg_ttfl_season": float(np.mean(scores)),
        "stddev_ttfl": float(np.std(scores)) if len(scores) >= 3 else 0,
        "home_avg": float(np.mean(home_scores)) if home_scores else 0,
        "away_avg": float(np.mean(away_scores)) if away_scores else 0,
    }
```

- [ ] **Step 2: Verify import works**

Run: `source venv/bin/activate && python -c "from sync.fetcher import fetch_today_scoreboard; print('fetcher OK')"`
Expected: `fetcher OK`

- [ ] **Step 3: Commit**

```bash
git add sync/fetcher.py
git commit -m "feat: NBA data fetcher (scoreboard, box scores, rosters, game logs)"
```

---

## Task 5: ESPN Injury Fetcher

**Files:**
- Create: `sync/injuries.py`

- [ ] **Step 1: Write the ESPN injury fetcher**

```python
# sync/injuries.py
"""Fetch player injury statuses from ESPN unofficial API."""
import httpx

# ESPN team IDs mapped to NBA tricodes
ESPN_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4,
    "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GSW": 9,
    "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MEM": 29,
    "MIA": 14, "MIL": 15, "MIN": 16, "NOP": 3, "NYK": 18,
    "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22,
    "SAC": 23, "SAS": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}

INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"


def fetch_team_injuries(team_tricode: str) -> list[dict]:
    """Fetch injuries for a single team.

    Returns list of dicts:
        {"name": str, "status": str, "detail": str}
    where status is one of: "Out", "Day-To-Day", "Questionable", "Doubtful"
    """
    espn_id = ESPN_TEAM_IDS.get(team_tricode)
    if espn_id is None:
        return []

    url = INJURY_URL.format(team_id=espn_id)
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    injuries = []
    for item in data.get("items", []):
        athlete = item.get("athlete", {})
        name = athlete.get("displayName", "")
        status = item.get("status", "")
        detail_type = item.get("type", {}).get("description", "")
        detail = item.get("details", {}).get("detail", detail_type)

        if name and status:
            injuries.append({
                "name": name,
                "status": status,
                "detail": detail,
            })

    return injuries


def fetch_all_injuries(teams: list[str] | None = None) -> dict[str, list[dict]]:
    """Fetch injuries for all teams (or a subset).

    Returns {team_tricode: [{"name", "status", "detail"}, ...]}
    """
    if teams is None:
        teams = list(ESPN_TEAM_IDS.keys())

    all_injuries = {}
    for tricode in teams:
        team_injuries = fetch_team_injuries(tricode)
        if team_injuries:
            all_injuries[tricode] = team_injuries

    return all_injuries


def match_injury_to_player(
    injury_name: str, players: list[dict]
) -> int | None:
    """Match an ESPN injury name to a player dict by fuzzy name matching.
    Players should have 'name' and 'id' keys.
    Returns player_id or None.
    """
    injury_lower = injury_name.lower().strip()
    for p in players:
        player_lower = p["name"].lower().strip()
        # Exact match
        if player_lower == injury_lower:
            return p["id"]
        # Last name match (handles "S. Gilgeous-Alexander" vs "Shai Gilgeous-Alexander")
        injury_last = injury_lower.split()[-1] if injury_lower else ""
        player_last = player_lower.split()[-1] if player_lower else ""
        if injury_last and injury_last == player_last:
            # Check first initial too if available
            if len(injury_lower.split()) >= 2 and len(player_lower.split()) >= 2:
                if injury_lower.split()[0][0] == player_lower.split()[0][0]:
                    return p["id"]
            elif injury_last == player_last:
                return p["id"]
    return None
```

- [ ] **Step 2: Quick smoke test**

Run: `source venv/bin/activate && python -c "from sync.injuries import fetch_team_injuries; print(fetch_team_injuries('LAL'))"`
Expected: List of injury dicts (or empty list if no injuries). No crash.

- [ ] **Step 3: Commit**

```bash
git add sync/injuries.py
git commit -m "feat: ESPN injury fetcher with team ID mapping"
```

---

## Task 6: Scoring Engine (6 Factors)

**Files:**
- Create: `sync/scoring.py`
- Create: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests for the scoring engine**

```python
# tests/test_scoring.py
from sync.scoring import (
    weighted_ttfl_average,
    matchup_factor,
    home_away_factor,
    fatigue_factor,
    trend_factor,
    consistency_factor,
    compute_performance_score,
)


def test_weighted_average_full_data():
    """L5=60, L10=55, L20=50 → (60×3 + 55×2 + 50×1) / 6 = 55.83"""
    score = weighted_ttfl_average(avg_l5=60, avg_l10=55, avg_l20=50)
    assert round(score, 2) == 55.83


def test_weighted_average_low_stats():
    """All zeros"""
    score = weighted_ttfl_average(avg_l5=0, avg_l10=0, avg_l20=0)
    assert score == 0


def test_matchup_factor_easy():
    """Opponent allows 10% more TTFL than average at this position → bonus"""
    # league avg 40, opponent allows 44 → factor = 44/40 = 1.1
    factor = matchup_factor(opponent_ttfl_at_position=44, league_avg_ttfl_at_position=40)
    assert round(factor, 2) == 1.10


def test_matchup_factor_tough():
    """Opponent allows 10% less → malus"""
    factor = matchup_factor(opponent_ttfl_at_position=36, league_avg_ttfl_at_position=40)
    assert round(factor, 2) == 0.90


def test_home_away_home_game():
    """Player at home with home_avg=55, away_avg=48, season_avg=51"""
    factor = home_away_factor(home_avg=55, away_avg=48, season_avg=51, is_home=True)
    # home delta = (55 - 51) / 51 = +0.078 → factor = 1.078
    assert round(factor, 3) == 1.078


def test_home_away_away_game():
    factor = home_away_factor(home_avg=55, away_avg=48, season_avg=51, is_home=False)
    # away delta = (48 - 51) / 51 = -0.059 → factor = 0.941
    assert round(factor, 3) == 0.941


def test_fatigue_b2b():
    """Back-to-back → -8%"""
    factor = fatigue_factor(days_rest=0)
    assert factor == 0.92


def test_fatigue_well_rested():
    """3+ days rest → +3%"""
    factor = fatigue_factor(days_rest=3)
    assert factor == 1.03


def test_fatigue_normal():
    """1-2 days rest → neutral"""
    assert fatigue_factor(days_rest=1) == 1.0
    assert fatigue_factor(days_rest=2) == 1.0


def test_trend_positive():
    """Scores trending up → bonus > 1.0"""
    scores = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58]  # clear uptrend
    factor = trend_factor(recent_scores=scores)
    assert factor > 1.0


def test_trend_negative():
    """Scores trending down → malus < 1.0"""
    scores = [58, 56, 54, 52, 50, 48, 46, 44, 42, 40]  # clear downtrend
    factor = trend_factor(recent_scores=scores)
    assert factor < 1.0


def test_trend_flat():
    """Flat scores → ~1.0"""
    scores = [50, 50, 50, 50, 50]
    factor = trend_factor(recent_scores=scores)
    assert round(factor, 2) == 1.0


def test_consistency_reliable():
    """Low stddev → bonus"""
    factor = consistency_factor(stddev=5, avg=50)
    assert factor > 1.0


def test_consistency_volatile():
    """High stddev → malus"""
    factor = consistency_factor(stddev=20, avg=50)
    assert factor < 1.0


def test_compute_performance_score():
    """Integration test: all factors combined"""
    score = compute_performance_score(
        avg_l5=60, avg_l10=55, avg_l20=50,
        opponent_ttfl_at_position=44, league_avg_ttfl_at_position=40,
        home_avg=55, away_avg=48, season_avg=51, is_home=True,
        days_rest=2,
        recent_scores=[50, 52, 54, 56, 58, 55, 53, 51, 49, 47],
        stddev=8,
    )
    assert isinstance(score, float)
    assert score > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync.scoring'`

- [ ] **Step 3: Write the scoring engine**

```python
# sync/scoring.py
"""6-factor performance scoring engine.

Factors and weights (from config):
  - weighted_avg:  35%  (L5×3 + L10×2 + L20×1) / 6
  - matchup:       25%  TTFL allowed by opponent at position
  - home_away:     10%  home/away split delta
  - fatigue:       10%  back-to-back / rest days
  - trend:         10%  linear regression slope on L10
  - consistency:   10%  stddev-based reliability
"""
import numpy as np
from sync.config import WEIGHTS, FATIGUE


def weighted_ttfl_average(avg_l5: float, avg_l10: float, avg_l20: float) -> float:
    """Weighted average: recent games count more. (L5×3 + L10×2 + L20×1) / 6"""
    return (avg_l5 * 3 + avg_l10 * 2 + avg_l20 * 1) / 6


def matchup_factor(
    opponent_ttfl_at_position: float, league_avg_ttfl_at_position: float
) -> float:
    """How much TTFL the opponent allows at this position vs league average.
    Returns multiplier (e.g. 1.10 = easy matchup, 0.90 = tough).
    """
    if league_avg_ttfl_at_position == 0:
        return 1.0
    return opponent_ttfl_at_position / league_avg_ttfl_at_position


def home_away_factor(
    home_avg: float, away_avg: float, season_avg: float, is_home: bool
) -> float:
    """Delta between player's home/away avg and season avg. Returns multiplier."""
    if season_avg == 0:
        return 1.0
    relevant_avg = home_avg if is_home else away_avg
    delta = (relevant_avg - season_avg) / season_avg
    return 1.0 + delta


def fatigue_factor(days_rest: int) -> float:
    """Fatigue modifier based on rest days since last game.
    0 days = back-to-back → -8%
    3+ days = well rested → +3%
    1-2 days = normal → neutral
    """
    if days_rest == 0:
        return 1.0 + FATIGUE["b2b"]  # 0.92
    elif days_rest >= 3:
        return 1.0 + FATIGUE["rest_3plus"]  # 1.03
    return 1.0


def trend_factor(recent_scores: list[int | float]) -> float:
    """Linear regression on recent scores. Positive slope = bonus, negative = malus.
    Scores should be ordered most recent first.
    Returns multiplier around 1.0.
    """
    if len(recent_scores) < 3:
        return 1.0

    # Reverse so index 0 = oldest, ascending time
    scores = list(reversed(recent_scores[:10]))
    x = np.arange(len(scores), dtype=float)
    y = np.array(scores, dtype=float)

    # Linear regression slope
    slope = np.polyfit(x, y, 1)[0]
    avg = np.mean(y)

    if avg == 0:
        return 1.0

    # Normalize: slope per game as % of average, capped at ±10%
    pct_change = slope / avg
    capped = max(-0.10, min(0.10, pct_change))
    return 1.0 + capped


def consistency_factor(stddev: float, avg: float) -> float:
    """Lower stddev (more consistent) = bonus. Higher = malus.
    Uses coefficient of variation (CV = stddev/avg).
    CV < 0.20 = reliable → bonus. CV > 0.35 = volatile → malus.
    """
    if avg == 0:
        return 1.0

    cv = stddev / avg
    # Map CV to multiplier: CV=0.15 → +3%, CV=0.25 → 0%, CV=0.40 → -5%
    # Linear interpolation centered around CV=0.25
    deviation = 0.25 - cv  # positive = good (low CV), negative = bad (high CV)
    modifier = deviation * 0.20  # scale factor
    capped = max(-0.05, min(0.05, modifier))
    return 1.0 + capped


def compute_performance_score(
    avg_l5: float, avg_l10: float, avg_l20: float,
    opponent_ttfl_at_position: float, league_avg_ttfl_at_position: float,
    home_avg: float, away_avg: float, season_avg: float, is_home: bool,
    days_rest: int,
    recent_scores: list[int | float],
    stddev: float,
) -> float:
    """Compute the final weighted performance score.

    The base is the weighted TTFL average, multiplied by each factor
    raised to its relative weight.
    """
    base = weighted_ttfl_average(avg_l5, avg_l10, avg_l20)

    factors = {
        "matchup": matchup_factor(opponent_ttfl_at_position, league_avg_ttfl_at_position),
        "home_away": home_away_factor(home_avg, away_avg, season_avg, is_home),
        "fatigue": fatigue_factor(days_rest),
        "trend": trend_factor(recent_scores),
        "consistency": consistency_factor(stddev, season_avg),
    }

    # Apply factors as weighted multipliers to the base
    # Score = base × (matchup^w_matchup) × (home_away^w_home) × ...
    # The weighted_avg factor is already the base (35%), so we apply the others
    combined_multiplier = 1.0
    non_base_total_weight = sum(
        WEIGHTS[k] for k in factors.keys()
    )
    for key, factor_value in factors.items():
        # Normalize weight so non-base factors sum to 1
        normalized_weight = WEIGHTS[key] / non_base_total_weight
        combined_multiplier *= factor_value ** normalized_weight

    return base * combined_multiplier
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add sync/scoring.py tests/test_scoring.py
git commit -m "feat: 6-factor scoring engine with tests"
```

---

## Task 7: Playoff Strategy Layer

**Files:**
- Create: `sync/strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_strategy.py
from sync.strategy import (
    classify_tiers,
    estimate_remaining_game_days,
    should_burn_elite,
    compute_strategy_adjustment,
)


def test_classify_tiers_basic():
    """Top 10 = elite, 11-25 = solid, 26-50 = filler"""
    player_scores = [(i, 100 - i) for i in range(1, 51)]  # id, score
    tiers = classify_tiers(player_scores)
    assert tiers[1] == "elite"    # rank 1
    assert tiers[10] == "elite"   # rank 10
    assert tiers[11] == "solid"   # rank 11
    assert tiers[25] == "solid"   # rank 25
    assert tiers[26] == "filler"  # rank 26
    assert tiers[50] == "filler"  # rank 50


def test_estimate_remaining_game_days():
    """Series 2-2 should estimate 2-3 remaining games in that series"""
    active_series = [
        {"home_wins": 2, "away_wins": 2, "round": 1},  # 1-3 games left
        {"home_wins": 3, "away_wins": 1, "round": 1},  # 1 game left
    ]
    days = estimate_remaining_game_days(active_series, current_round=1)
    assert days > 0
    assert isinstance(days, int)


def test_should_burn_elite_good_spot():
    """High score tonight, no clearly better future spot → burn"""
    result = should_burn_elite(
        tonight_score=75,
        best_future_score=70,
        elites_remaining=3,
        game_days_remaining=10,
    )
    assert result is True


def test_should_burn_elite_save():
    """Better spot coming soon → save"""
    result = should_burn_elite(
        tonight_score=60,
        best_future_score=80,
        elites_remaining=2,
        game_days_remaining=15,
    )
    assert result is False


def test_strategy_adjustment_playoffs():
    """Strategy score adjusts the raw perf score"""
    adjusted = compute_strategy_adjustment(
        perf_score=70,
        tier="elite",
        is_home=True,
        series_score=(2, 2),
        elites_remaining=3,
        game_days_remaining=15,
    )
    assert isinstance(adjusted, float)
    # Home game in tight series for elite → should get a boost
    assert adjusted > 70


def test_strategy_adjustment_filler_no_boost():
    """Fillers don't get strategy penalty for burning"""
    adjusted = compute_strategy_adjustment(
        perf_score=40,
        tier="filler",
        is_home=False,
        series_score=(3, 1),
        elites_remaining=3,
        game_days_remaining=15,
    )
    # Filler should be close to perf_score, slight away malus
    assert adjusted <= 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync.strategy'`

- [ ] **Step 3: Write the strategy layer**

```python
# sync/strategy.py
"""Playoff strategy layer.

Manages player capital (elite/solid/filler tiers),
estimates remaining game days, and decides burn-or-save.
"""
from sync.config import BURN_THRESHOLD


def classify_tiers(player_scores: list[tuple[int, float]]) -> dict[int, str]:
    """Classify players into tiers based on their performance score ranking.

    Args:
        player_scores: list of (player_id, avg_perf_score) sorted by score desc.

    Returns:
        {player_id: "elite"|"solid"|"filler"}
    """
    # Sort descending by score
    sorted_players = sorted(player_scores, key=lambda x: x[1], reverse=True)
    tiers = {}
    for rank, (player_id, _) in enumerate(sorted_players, start=1):
        if rank <= 10:
            tiers[player_id] = "elite"
        elif rank <= 25:
            tiers[player_id] = "solid"
        else:
            tiers[player_id] = "filler"
    return tiers


def estimate_remaining_game_days(
    active_series: list[dict], current_round: int
) -> int:
    """Estimate total remaining game days in the playoffs.

    For each active series, estimate remaining games based on score.
    Add estimates for future rounds.
    """
    remaining = 0

    for series in active_series:
        hw = series["home_wins"]
        aw = series["away_wins"]
        max_wins = max(hw, aw)
        # Games played so far
        played = hw + aw
        # Min remaining = 4 - max_wins (clinch), max = 7 - played
        min_left = 4 - max_wins
        max_left = 7 - played
        # Estimate: weighted toward the middle
        est = (min_left + max_left) / 2
        remaining += max(0, est)

    # Future rounds: estimate 6 games per round (avg series length)
    future_rounds = 4 - current_round  # conf semis=1, conf finals=2, finals=3 remaining from R1
    remaining += future_rounds * 6

    # Convert to game DAYS (not every day has games; ~60% of days have games in playoffs)
    game_days = int(remaining * 0.7)
    return max(1, game_days)


def should_burn_elite(
    tonight_score: float,
    best_future_score: float,
    elites_remaining: int,
    game_days_remaining: int,
) -> bool:
    """Decide whether to use an elite player tonight or save them.

    Burns if tonight's score is within BURN_THRESHOLD of the best future opportunity,
    or if there are enough elites relative to remaining game days.
    """
    # If future score is significantly better, save
    if best_future_score > tonight_score * (1 + BURN_THRESHOLD):
        return False

    # If running low on elites relative to days, be more conservative
    if elites_remaining <= 2 and game_days_remaining > 10:
        # Only burn if tonight is clearly great
        return tonight_score >= best_future_score

    return True


def compute_strategy_adjustment(
    perf_score: float,
    tier: str,
    is_home: bool,
    series_score: tuple[int, int],
    elites_remaining: int,
    game_days_remaining: int,
) -> float:
    """Apply playoff strategy adjustments to a performance score.

    Boosts:
    - Home game in tight series (2-2, 2-1, 1-2) → +5%
    - Elimination game → +8% (players go harder)
    - Filler in a "save elite" spot → +3% (encourage picking fillers)

    Penalties:
    - Elite when better future spot exists → -10%
    - Away game in opponent's home court advantage → -3%
    """
    adjustment = 1.0
    hw, aw = series_score
    series_tight = abs(hw - aw) <= 1

    # Home court bonus (more significant in playoffs)
    if is_home:
        adjustment += 0.03
        if series_tight:
            adjustment += 0.02  # extra for tight series

    # Elimination game bonus
    if hw == 3 or aw == 3:
        adjustment += 0.08

    # Tier-based strategy
    if tier == "elite":
        # Penalty if elites are scarce and many days remain
        elite_ratio = elites_remaining / max(1, game_days_remaining)
        if elite_ratio < 0.2:  # fewer than 1 elite per 5 days
            adjustment -= 0.05  # discourage burning
    elif tier == "filler":
        # Slight boost for fillers when we want to save elites
        elite_ratio = elites_remaining / max(1, game_days_remaining)
        if elite_ratio < 0.25:
            adjustment += 0.03

    # Away penalty
    if not is_home:
        adjustment -= 0.03

    return perf_score * adjustment
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_strategy.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add sync/strategy.py tests/test_strategy.py
git commit -m "feat: playoff strategy layer with tier classification and burn-or-save logic"
```

---

## Task 8: Advisor (Argumentaire Generator)

**Files:**
- Create: `sync/advisor.py`
- Create: `tests/test_advisor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_advisor.py
from sync.advisor import generate_argumentaire, generate_verdict


def test_generate_argumentaire_has_pros_and_cons():
    context = {
        "player_name": "Nikola Jokic",
        "team": "DEN",
        "opponent": "OKC",
        "is_home": True,
        "avg_l5": 62.4,
        "avg_season": 54.1,
        "matchup_rank": 2,  # 2nd worst defense at position
        "matchup_position": "centers",
        "series_score": (2, 2),
        "game_number": 5,
        "tier": "elite",
        "elites_remaining": 3,
        "game_days_remaining": 18,
        "days_rest": 2,
        "stddev": 8,
        "floor": 45,
        "ceiling": 78,
        "injury_status": None,
        "teammate_out": None,
    }
    pros, cons = generate_argumentaire(context)
    assert len(pros) > 0
    assert len(cons) > 0
    assert any("feu" in p.lower() or "forme" in p.lower() or "avg" in p.lower() for p in pros)


def test_generate_argumentaire_injury_teammate():
    context = {
        "player_name": "Paul George",
        "team": "PHI",
        "opponent": "BOS",
        "is_home": False,
        "avg_l5": 45,
        "avg_season": 42,
        "matchup_rank": 15,
        "matchup_position": "forwards",
        "series_score": (1, 3),
        "game_number": 5,
        "tier": "solid",
        "elites_remaining": 4,
        "game_days_remaining": 20,
        "days_rest": 1,
        "stddev": 14,
        "floor": 20,
        "ceiling": 68,
        "injury_status": None,
        "teammate_out": "Joel Embiid",
    }
    pros, cons = generate_argumentaire(context)
    # Should mention teammate absence as a pro (more usage)
    assert any("embiid" in p.lower() for p in pros)


def test_generate_verdict_burn():
    verdict = generate_verdict(
        should_burn=True,
        tier="elite",
        tonight_score=75,
        best_future_description="Game 7 DEN-OKC à domicile mercredi",
    )
    assert "JOUE" in verdict.upper() or "BON SOIR" in verdict.upper()


def test_generate_verdict_save():
    verdict = generate_verdict(
        should_burn=False,
        tier="elite",
        tonight_score=60,
        best_future_description="Game 5 vs MIL à domicile vendredi",
    )
    assert "GARDE" in verdict.upper() or "SAVE" in verdict.upper()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_advisor.py -v`
Expected: FAIL

- [ ] **Step 3: Write the advisor**

```python
# sync/advisor.py
"""Generate POUR / CONTRE / VERDICT argumentaires for each player."""


def generate_argumentaire(context: dict) -> tuple[list[str], list[str]]:
    """Generate pros and cons lists for a player pick.

    Args:
        context: dict with keys:
            player_name, team, opponent, is_home,
            avg_l5, avg_season, matchup_rank, matchup_position,
            series_score, game_number, tier,
            elites_remaining, game_days_remaining,
            days_rest, stddev, floor, ceiling,
            injury_status, teammate_out

    Returns:
        (pros: list[str], cons: list[str])
    """
    pros = []
    cons = []

    name = context["player_name"]
    avg_l5 = context["avg_l5"]
    avg_season = context["avg_season"]

    # --- Form ---
    if avg_l5 > avg_season * 1.10:
        pct = round((avg_l5 / avg_season - 1) * 100)
        pros.append(f"En feu : {avg_l5:.1f} TTFL avg sur les 5 derniers matchs (+{pct}% vs saison)")
    elif avg_l5 < avg_season * 0.90:
        pct = round((1 - avg_l5 / avg_season) * 100)
        cons.append(f"En méforme : {avg_l5:.1f} TTFL avg L5 (-{pct}% vs saison {avg_season:.1f})")

    # --- Matchup ---
    matchup_rank = context["matchup_rank"]
    position = context["matchup_position"]
    opponent = context["opponent"]
    if matchup_rank <= 5:
        pros.append(f"Matchup juteux : {opponent} encaisse le {matchup_rank}e plus de pts TTFL aux {position} en playoffs")
    elif matchup_rank >= 25:
        cons.append(f"Matchup difficile : {opponent} est top {30 - matchup_rank + 1} défense aux {position}")

    # --- Home court ---
    hw, aw = context["series_score"]
    game_num = context["game_number"]
    if context["is_home"]:
        series_desc = f"{hw}-{aw}"
        tight = abs(hw - aw) <= 1
        if tight:
            pros.append(f"Game {game_num} à domicile, série {series_desc} (enjeu max, crowd factor)")
        else:
            pros.append(f"Game {game_num} à domicile")
    else:
        cons.append(f"Match à l'extérieur (Game {game_num})")

    # --- Elimination ---
    if hw == 3 or aw == 3:
        if (hw == 3 and not context["is_home"]) or (aw == 3 and context["is_home"]):
            pros.append("Match d'élimination pour l'adversaire : intensité max des deux côtés")
        else:
            pros.append("Possible match de clôture : motivation pour finir la série")

    # --- Fatigue ---
    days_rest = context["days_rest"]
    if days_rest == 0:
        cons.append("Back-to-back : risque de fatigue et minutes réduites")
    elif days_rest >= 3:
        pros.append(f"{days_rest} jours de repos : frais et reposé")

    # --- Consistency ---
    floor = context["floor"]
    ceiling = context["ceiling"]
    stddev = context["stddev"]
    if stddev < 10:
        pros.append(f"Floor très haut : jamais sous {floor} TTFL sur les 20 derniers matchs")
    elif stddev > 18:
        cons.append(f"Joueur volatile : floor {floor}, ceiling {ceiling} (écart important)")

    # --- Teammate injury (usage boost) ---
    teammate_out = context.get("teammate_out")
    if teammate_out:
        pros.append(f"Sans {teammate_out} : plus de ballons, usage en hausse")

    # --- Player injury ---
    injury = context.get("injury_status")
    if injury:
        cons.append(f"Statut {injury} : risque de minutes limitées ou forfait de dernière minute")

    # --- Strategy (capital) ---
    tier = context["tier"]
    elites = context["elites_remaining"]
    days = context["game_days_remaining"]

    if tier == "elite":
        cons.append(f"C'est un de tes {elites} elites restants pour ~{days} jours de match")
    elif tier == "solid":
        if elites > 3:
            pros.append("Pick solide qui préserve ton capital elite")
    elif tier == "filler":
        pros.append("Pick économique : garde tes cartouches pour les gros soirs")

    return pros, cons


def generate_verdict(
    should_burn: bool,
    tier: str,
    tonight_score: float,
    best_future_description: str,
) -> str:
    """Generate verdict text for the recommendation.

    Args:
        should_burn: True if recommending to pick tonight
        tier: "elite", "solid", "filler"
        tonight_score: estimated score for tonight
        best_future_description: e.g. "Game 7 DEN-OKC à domicile mercredi"
    """
    if tier == "filler":
        return (
            f"Pick safe à {tonight_score:.0f} estimé. "
            "Bon choix pour une soirée sans spot premium — préserve tes meilleurs joueurs."
        )

    if should_burn:
        return (
            f"Excellent spot ce soir ({tonight_score:.0f} estimé). "
            f"Recommandation : JOUE-LE. Meilleur prochain spot identifié : {best_future_description}."
        )
    else:
        return (
            f"Bon joueur mais meilleur spot à venir : {best_future_description}. "
            f"Recommandation : GARDE-LE pour maximiser son potentiel."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_advisor.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add sync/advisor.py tests/test_advisor.py
git commit -m "feat: argumentaire generator with pros/cons/verdict logic"
```

---

## Task 9: Cron Orchestrator

**Files:**
- Create: `sync/main.py`

- [ ] **Step 1: Write the main orchestrator**

```python
# sync/main.py
"""Cron orchestrator. Runs the full sync pipeline:

1. Fetch today's games + yesterday's results
2. Fetch/update player game logs and box scores
3. Fetch injuries from ESPN
4. Compute player aggregates
5. Compute scoring for tonight's players
6. Apply playoff strategy layer
7. Generate argumentaires for top 50
8. Push everything to Supabase
"""
import sys
import time
import traceback
from datetime import date, datetime, timedelta

import numpy as np

from sync import db
from sync.config import NBA_API_DELAY
from sync.fetcher import (
    fetch_today_scoreboard,
    parse_today_games,
    fetch_live_box_score,
    fetch_player_game_logs_nba_api,
    fetch_team_rosters,
    compute_player_aggregates,
)
from sync.injuries import fetch_all_injuries, match_injury_to_player
from sync.scoring import compute_performance_score
from sync.strategy import (
    classify_tiers,
    estimate_remaining_game_days,
    should_burn_elite,
    compute_strategy_adjustment,
)
from sync.advisor import generate_argumentaire, generate_verdict
from sync.ttfl import compute_ttfl_from_game_log


def run_sync():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting sync...")
    client = db.get_client()
    log_id = db.start_sync_log(client)

    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        players_updated = 0

        # --- Step 1: Fetch today's scoreboard ---
        print("  Fetching scoreboard...")
        scoreboard = fetch_today_scoreboard()
        today_games = parse_today_games(scoreboard, today)
        db.upsert_games(client, today_games)
        print(f"  {len(today_games)} games today")

        # --- Step 2: Fetch yesterday's box scores (for actual_score updates) ---
        yesterday_games = db.get_today_games(client, yesterday)
        for game in yesterday_games:
            if game["status"] != "final":
                continue
            print(f"  Fetching box score for {game['id']}...")
            box_players = fetch_live_box_score(game["id"])
            game_logs = []
            for bp in box_players:
                game_logs.append({
                    "player_id": bp["player_id"],
                    "game_id": bp["game_id"],
                    "date": bp["date"],
                    "pts": bp["pts"], "reb": bp["reb"], "ast": bp["ast"],
                    "stl": bp["stl"], "blk": bp["blk"],
                    "fgm": bp["fgm"], "fga": bp["fga"],
                    "tpm": bp["tpm"], "tpa": bp["tpa"],
                    "ftm": bp["ftm"], "fta": bp["fta"],
                    "tov": bp["tov"], "minutes": bp["minutes"],
                    "ttfl_score": bp["ttfl_score"],
                    "is_home": bp["is_home"],
                })
            db.upsert_game_logs(client, game_logs)

        # --- Step 3: Fetch rosters + update players ---
        print("  Fetching rosters...")
        rosters = fetch_team_rosters()
        all_players_list = []
        for tricode, players in rosters.items():
            for p in players:
                all_players_list.append(p)
        db.upsert_players(client, all_players_list)
        players_updated = len(all_players_list)
        print(f"  {players_updated} players updated")

        # --- Step 4: Fetch injuries ---
        print("  Fetching injuries...")
        playing_teams = set()
        for g in today_games:
            playing_teams.add(g["home_team"])
            playing_teams.add(g["away_team"])

        injuries = fetch_all_injuries(list(playing_teams))
        all_players_db = db.get_all_players(client)

        for team_tricode, team_injuries in injuries.items():
            team_players = [p for p in all_players_db if p["team"] == team_tricode]
            for inj in team_injuries:
                player_id = match_injury_to_player(inj["name"], team_players)
                if player_id:
                    db.upsert_players(client, [{
                        "id": player_id,
                        "injury_status": inj["status"],
                        "injury_detail": inj["detail"],
                    }])

        # Clear injuries for players not in injury report
        for p in all_players_db:
            if p["team"] in playing_teams:
                team_inj_names = [
                    i["name"].lower()
                    for i in injuries.get(p["team"], [])
                ]
                is_injured = any(
                    p["name"].lower().split()[-1] in name
                    for name in team_inj_names
                )
                if not is_injured and p.get("injury_status"):
                    db.upsert_players(client, [{
                        "id": p["id"],
                        "injury_status": None,
                        "injury_detail": None,
                    }])

        # --- Step 5: Update player aggregates for tonight's players ---
        print("  Computing player aggregates...")
        all_players_db = db.get_all_players(client)  # refresh after injury updates
        tonight_player_ids = set()
        for g in today_games:
            for p in all_players_db:
                if p["team"] in (g["home_team"], g["away_team"]):
                    tonight_player_ids.add(p["id"])

        for pid in tonight_player_ids:
            logs = db.get_player_game_logs(client, pid, limit=20)
            if not logs:
                # Try fetching from nba_api if no local logs
                nba_logs = fetch_player_game_logs_nba_api(pid)
                if nba_logs:
                    game_log_rows = []
                    for nl in nba_logs[:20]:
                        ttfl = compute_ttfl_from_game_log(nl)
                        game_log_rows.append({
                            "player_id": pid,
                            "game_id": nl.get("Game_ID", f"unknown_{pid}_{nl.get('GAME_DATE', '')}"),
                            "date": nl.get("GAME_DATE", ""),
                            "pts": nl.get("PTS", 0), "reb": nl.get("REB", 0),
                            "ast": nl.get("AST", 0), "stl": nl.get("STL", 0),
                            "blk": nl.get("BLK", 0),
                            "fgm": nl.get("FGM", 0), "fga": nl.get("FGA", 0),
                            "tpm": nl.get("FG3M", 0), "tpa": nl.get("FG3A", 0),
                            "ftm": nl.get("FTM", 0), "fta": nl.get("FTA", 0),
                            "tov": nl.get("TOV", 0),
                            "minutes": nl.get("MIN", 0),
                            "ttfl_score": ttfl,
                            "is_home": "vs." in nl.get("MATCHUP", ""),
                        })
                    db.upsert_game_logs(client, game_log_rows)
                    logs = game_log_rows

            if logs:
                aggs = compute_player_aggregates(logs)
                aggs["id"] = pid
                aggs["updated_at"] = datetime.utcnow().isoformat()
                db.upsert_players(client, [aggs])

        # --- Step 6: Score tonight's players ---
        print("  Scoring players...")
        all_players_db = db.get_all_players(client)  # refresh
        picked_ids = db.get_picked_player_ids(client, mode="playoffs")
        active_series = db.get_active_series(client)

        # Build scoring for each eligible player
        scored_players = []
        for g in today_games:
            if g["status"] == "final":
                continue

            for p in all_players_db:
                if p["team"] not in (g["home_team"], g["away_team"]):
                    continue
                if p["id"] in picked_ids:
                    continue
                if p.get("injury_status") in ("Out", "Doubtful"):
                    continue

                is_home = p["team"] == g["home_team"]
                opponent = g["away_team"] if is_home else g["home_team"]
                opp_defense = db.get_team_defense(client, opponent)

                # Determine position-based matchup value
                league_avg = 40  # rough default
                opp_ttfl = league_avg
                if opp_defense:
                    pos_key = f"vs_{p['position'].lower()}s_ttfl_avg"
                    if p["position"] == "G":
                        pos_key = "vs_guards_ttfl_avg"
                    elif p["position"] == "F":
                        pos_key = "vs_forwards_ttfl_avg"
                    else:
                        pos_key = "vs_centers_ttfl_avg"
                    opp_ttfl = opp_defense.get(pos_key, league_avg) or league_avg

                # Get recent scores for trend
                logs = db.get_player_game_logs(client, p["id"], limit=10)
                recent_scores = [l["ttfl_score"] for l in logs]

                # Days rest
                if logs:
                    last_game_date = logs[0].get("date", "")
                    try:
                        from datetime import datetime as dt
                        last_dt = dt.strptime(str(last_game_date), "%Y-%m-%d").date()
                        days_rest = (date.today() - last_dt).days - 1
                    except (ValueError, TypeError):
                        days_rest = 2
                else:
                    days_rest = 2

                perf_score = compute_performance_score(
                    avg_l5=p.get("avg_ttfl_l5", 0) or 0,
                    avg_l10=p.get("avg_ttfl_l10", 0) or 0,
                    avg_l20=p.get("avg_ttfl_l20", 0) or 0,
                    opponent_ttfl_at_position=opp_ttfl,
                    league_avg_ttfl_at_position=league_avg,
                    home_avg=p.get("home_avg", 0) or 0,
                    away_avg=p.get("away_avg", 0) or 0,
                    season_avg=p.get("avg_ttfl_season", 0) or 0,
                    is_home=is_home,
                    days_rest=days_rest,
                    recent_scores=recent_scores,
                    stddev=p.get("stddev_ttfl", 0) or 0,
                )

                scored_players.append({
                    "player": p,
                    "game": g,
                    "perf_score": perf_score,
                    "is_home": is_home,
                    "opponent": opponent,
                    "days_rest": days_rest,
                    "recent_scores": recent_scores,
                })

        # --- Step 7: Apply playoff strategy ---
        print("  Applying strategy layer...")
        # Classify tiers
        available_scores = [(sp["player"]["id"], sp["perf_score"]) for sp in scored_players]
        tiers = classify_tiers(available_scores)

        current_round = max((s["round"] for s in active_series), default=1)
        game_days_remaining = estimate_remaining_game_days(active_series, current_round)
        elites_remaining = sum(1 for t in tiers.values() if t == "elite")

        for sp in scored_players:
            pid = sp["player"]["id"]
            tier = tiers.get(pid, "filler")
            sp["tier"] = tier

            # Find series for this game
            game = sp["game"]
            series = None
            for s in active_series:
                teams = {s["home_team"], s["away_team"]}
                if game["home_team"] in teams and game["away_team"] in teams:
                    series = s
                    break

            series_score = (
                (series["home_wins"], series["away_wins"]) if series else (0, 0)
            )

            strategy_score = compute_strategy_adjustment(
                perf_score=sp["perf_score"],
                tier=tier,
                is_home=sp["is_home"],
                series_score=series_score,
                elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
            )
            sp["strategy_score"] = strategy_score
            sp["estimated_score"] = strategy_score
            sp["series_score"] = series_score
            sp["game_number"] = game.get("game_number", 0) or 0

        # Sort by estimated score descending, take top 50
        scored_players.sort(key=lambda x: x["estimated_score"], reverse=True)
        top_50 = scored_players[:50]

        # --- Step 8: Generate argumentaires ---
        print("  Generating argumentaires...")
        recommendations = []
        for rank, sp in enumerate(top_50, start=1):
            p = sp["player"]
            logs = sp["recent_scores"]
            floor_val = min(logs) if logs else 0
            ceiling_val = max(logs) if logs else 0

            # Find top 3 matchup rank for this position
            same_pos = [
                s for s in scored_players if s["player"]["position"] == p["position"]
            ]
            same_pos.sort(key=lambda x: x["perf_score"], reverse=True)
            matchup_rank = next(
                (i for i, s in enumerate(same_pos, 1) if s["player"]["id"] == p["id"]),
                15,
            )

            # Check for injured teammate
            teammate_out = None
            team_players = [
                s["player"] for s in scored_players if s["player"]["team"] == p["team"]
            ]
            for tp in all_players_db:
                if tp["team"] == p["team"] and tp.get("injury_status") == "Out":
                    if (tp.get("usage_rate", 0) or 0) > 20:
                        teammate_out = tp["name"]
                        break

            context = {
                "player_name": p["name"],
                "team": p["team"],
                "opponent": sp["opponent"],
                "is_home": sp["is_home"],
                "avg_l5": p.get("avg_ttfl_l5", 0) or 0,
                "avg_season": p.get("avg_ttfl_season", 0) or 0,
                "matchup_rank": matchup_rank,
                "matchup_position": {
                    "G": "guards", "F": "forwards", "C": "centers"
                }.get(p["position"], "forwards"),
                "series_score": sp["series_score"],
                "game_number": sp["game_number"],
                "tier": sp["tier"],
                "elites_remaining": elites_remaining,
                "game_days_remaining": game_days_remaining,
                "days_rest": sp["days_rest"],
                "stddev": p.get("stddev_ttfl", 0) or 0,
                "floor": floor_val,
                "ceiling": ceiling_val,
                "injury_status": p.get("injury_status"),
                "teammate_out": teammate_out,
            }

            pros, cons = generate_argumentaire(context)

            # Burn-or-save for verdict
            burn = should_burn_elite(
                tonight_score=sp["estimated_score"],
                best_future_score=sp["estimated_score"] * 0.95,  # simplified: assume future is ~95% of tonight
                elites_remaining=elites_remaining,
                game_days_remaining=game_days_remaining,
            )
            verdict = generate_verdict(
                should_burn=burn,
                tier=sp["tier"],
                tonight_score=sp["estimated_score"],
                best_future_description="prochain match à domicile",
            )

            # Tags
            tags = []
            if sp["is_home"]:
                tags.append("home")
            if p.get("avg_ttfl_l5", 0) and p.get("avg_ttfl_season", 0):
                if p["avg_ttfl_l5"] > p["avg_ttfl_season"] * 1.1:
                    tags.append("hot")
            if (p.get("stddev_ttfl", 0) or 0) > 15:
                tags.append("volatile")
            if rank <= 3:
                tags.append("reco_du_soir")

            recommendations.append({
                "date": today.isoformat(),
                "player_id": p["id"],
                "rank": rank,
                "estimated_score": round(sp["estimated_score"], 1),
                "perf_score": round(sp["perf_score"], 1),
                "matchup_score": round(sp.get("matchup_score", 0), 1),
                "strategy_score": round(sp.get("strategy_score", 0), 1),
                "pros": pros,
                "cons": cons,
                "verdict": verdict,
                "tier": sp["tier"],
                "tags": tags,
                "computed_at": datetime.utcnow().isoformat(),
            })

        # --- Step 9: Push to Supabase ---
        print(f"  Pushing {len(recommendations)} recommendations...")
        db.replace_recommendations(client, recommendations, today)

        db.finish_sync_log(client, log_id, players_updated)
        print(f"[{datetime.now():%H:%M}] Sync complete! {len(recommendations)} players scored.")

    except Exception as e:
        traceback.print_exc()
        db.fail_sync_log(client, log_id, str(e))
        print(f"[{datetime.now():%H:%M}] Sync FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_sync()
```

- [ ] **Step 2: Verify it runs (dry test — will fail without Supabase creds but should import cleanly)**

Run: `source venv/bin/activate && python -c "from sync.main import run_sync; print('main.py imports OK')"`
Expected: `main.py imports OK`

- [ ] **Step 3: Commit**

```bash
git add sync/main.py
git commit -m "feat: cron orchestrator — full sync pipeline"
```

- [ ] **Step 4: Set up crontab (after Supabase is configured)**

Add to crontab:

```bash
crontab -e
```

Add these lines (adjust paths):

```cron
0 7 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 12 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 17 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 22 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
```

---

## Task 10: Frontend — Project Setup + Layout

**Files:**
- Create: `web/package.json`
- Create: `web/next.config.ts`
- Create: `web/tailwind.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/src/types/index.ts`
- Create: `web/src/lib/supabase.ts`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/components/BottomNav.tsx`
- Create: `web/public/manifest.json`

- [ ] **Step 1: Scaffold the Next.js project**

Run:
```bash
cd /home/isow/workspace/perso/nba-fantasy
npx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm
```

When prompted, accept defaults (no Turbopack is fine).

- [ ] **Step 2: Install additional dependencies**

Run:
```bash
cd /home/isow/workspace/perso/nba-fantasy/web
npm install @supabase/supabase-js
npm install -D @ducanh2912/next-pwa
```

- [ ] **Step 3: Create TypeScript types**

```typescript
// web/src/types/index.ts

export interface Player {
  id: number;
  name: string;
  team: string;
  position: string;
  injury_status: string | null;
  injury_detail: string | null;
  avg_ttfl_l5: number;
  avg_ttfl_l10: number;
  avg_ttfl_l20: number;
  avg_ttfl_season: number;
  stddev_ttfl: number;
  home_avg: number;
  away_avg: number;
  usage_rate: number;
  updated_at: string;
}

export interface Game {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  tip_off: string | null;
  series_id: number | null;
  game_number: number | null;
  status: string;
}

export interface Series {
  id: number;
  round: number;
  home_team: string;
  away_team: string;
  home_wins: number;
  away_wins: number;
  status: string;
}

export interface Recommendation {
  id: number;
  date: string;
  player_id: number;
  rank: number;
  estimated_score: number;
  perf_score: number;
  matchup_score: number;
  strategy_score: number | null;
  pros: string[];
  cons: string[];
  verdict: string;
  tier: "elite" | "solid" | "filler";
  tags: string[];
  computed_at: string;
}

export interface Pick {
  id: number;
  player_id: number;
  game_id: string;
  date: string;
  mode: "regular" | "playoffs";
  estimated_score: number | null;
  actual_score: number | null;
  picked_at: string;
}

export interface SyncLog {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  players_updated: number;
  error_message: string | null;
}

// Joined types for display
export interface RecommendationWithPlayer extends Recommendation {
  player: Player;
  game: Game;
}
```

- [ ] **Step 4: Create Supabase client**

```typescript
// web/src/lib/supabase.ts
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseKey);
```

Create `web/.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

- [ ] **Step 5: Create BottomNav component**

```tsx
// web/src/components/BottomNav.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "Ce soir", icon: "🏀" },
  { href: "/picks", label: "Mes picks", icon: "📋" },
  { href: "/strategy", label: "Stratégie", icon: "📊" },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-gray-950 border-t border-gray-800 z-50">
      <div className="flex max-w-lg mx-auto">
        {tabs.map((tab) => {
          const active = tab.href === "/"
            ? pathname === "/"
            : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex-1 flex flex-col items-center py-2.5 text-xs ${
                active
                  ? "text-blue-400 border-t-2 border-blue-400"
                  : "text-gray-500"
              }`}
            >
              <span className="text-lg">{tab.icon}</span>
              <span className="mt-0.5">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
```

- [ ] **Step 6: Create root layout**

Replace the generated `web/src/app/layout.tsx`:

```tsx
// web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TTFL Advisor",
  description: "Outil d'aide à la décision pour la TrashTalk Fantasy League",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen`}>
        <main className="max-w-lg mx-auto pb-20">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
```

- [ ] **Step 7: Create PWA manifest**

```json
// web/public/manifest.json
{
  "name": "TTFL Advisor",
  "short_name": "TTFL",
  "description": "Aide à la décision pour la TrashTalk Fantasy League",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

Create placeholder icons:
```bash
mkdir -p web/public/icons
# Generate simple placeholder icons (replace with real ones later)
convert -size 192x192 xc:'#3b82f6' -gravity center -fill white -pointsize 48 -annotate 0 'TTFL' web/public/icons/icon-192.png 2>/dev/null || echo "Install imagemagick for icons, or add PNGs manually"
convert -size 512x512 xc:'#3b82f6' -gravity center -fill white -pointsize 120 -annotate 0 'TTFL' web/public/icons/icon-512.png 2>/dev/null || echo "Add icons manually to web/public/icons/"
```

- [ ] **Step 8: Update next.config.ts for PWA**

```typescript
// web/next.config.ts
import type { NextConfig } from "next";
import withPWAInit from "@ducanh2912/next-pwa";

const withPWA = withPWAInit({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {};

export default withPWA(nextConfig);
```

- [ ] **Step 9: Verify dev server starts**

Run:
```bash
cd /home/isow/workspace/perso/nba-fantasy/web && npm run dev
```
Expected: Server starts on http://localhost:3000. Page shows default content with bottom nav.

- [ ] **Step 10: Commit**

```bash
cd /home/isow/workspace/perso/nba-fantasy
git add web/src/types/index.ts web/src/lib/supabase.ts web/src/app/layout.tsx web/src/components/BottomNav.tsx web/public/manifest.json web/next.config.ts web/.env.local
git commit -m "feat: Next.js project setup with Supabase client, layout, bottom nav, PWA manifest"
```

---

## Task 11: Frontend — "Ce soir" (Home Page)

**Files:**
- Create: `web/src/components/SyncStatus.tsx`
- Create: `web/src/components/GamesCollapsible.tsx`
- Create: `web/src/components/StrategyBanner.tsx`
- Create: `web/src/components/RecommendationCard.tsx`
- Create: `web/src/components/PlayerList.tsx`
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Create SyncStatus component**

```tsx
// web/src/components/SyncStatus.tsx
"use client";

import { SyncLog } from "@/types";

export default function SyncStatus({ sync }: { sync: SyncLog | null }) {
  if (!sync) return null;

  const finishedAt = sync.finished_at ? new Date(sync.finished_at) : null;
  const isStale = finishedAt
    ? Date.now() - finishedAt.getTime() > 12 * 60 * 60 * 1000
    : true;
  const isError = sync.status === "error";

  const timeStr = finishedAt
    ? finishedAt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : "...";
  const dateStr = finishedAt
    ? finishedAt.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })
    : "";

  const isToday = finishedAt?.toDateString() === new Date().toDateString();

  return (
    <div className="flex items-center gap-1.5 px-4 py-1">
      <div
        className={`w-1.5 h-1.5 rounded-full ${
          isError ? "bg-red-500" : isStale ? "bg-orange-400" : "bg-green-500"
        }`}
      />
      <span className="text-xs text-gray-500">
        Dernière synchro : {isToday ? `aujourd'hui à ${timeStr}` : `${dateStr} à ${timeStr}`}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Create GamesCollapsible component**

```tsx
// web/src/components/GamesCollapsible.tsx
"use client";

import { useState } from "react";
import { Game, Series } from "@/types";

interface Props {
  games: Game[];
  series: Series[];
}

export default function GamesCollapsible({ games, series }: Props) {
  const [open, setOpen] = useState(false);

  const getSeriesForGame = (game: Game) =>
    series.find(
      (s) =>
        (s.home_team === game.home_team && s.away_team === game.away_team) ||
        (s.home_team === game.away_team && s.away_team === game.home_team)
    );

  const formatTipOff = (tipOff: string | null) => {
    if (!tipOff) return "";
    const d = new Date(tipOff);
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="mx-3 bg-gray-900 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3.5 py-2.5 flex justify-between items-center"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-gray-100">🏀 Matchs du soir</span>
          <span className="bg-gray-950 text-gray-500 text-xs px-1.5 py-0.5 rounded">
            {games.length}
          </span>
        </div>
        <span className="text-gray-500 text-sm">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-gray-950 px-3.5 py-2 flex flex-col gap-1.5">
          {games.map((game) => {
            const s = getSeriesForGame(game);
            return (
              <div
                key={game.id}
                className="flex justify-between items-center text-sm py-1"
              >
                <div className="flex items-center gap-2">
                  <span className="font-bold text-gray-100 min-w-[100px]">
                    {game.home_team} vs {game.away_team}
                  </span>
                  {game.game_number && (
                    <span className="bg-green-950 text-green-500 text-[0.7em] px-1.5 py-0.5 rounded">
                      G{game.game_number}
                    </span>
                  )}
                </div>
                <span className="text-gray-500 text-xs">
                  {formatTipOff(game.tip_off)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create StrategyBanner component**

```tsx
// web/src/components/StrategyBanner.tsx
import { Recommendation } from "@/types";

interface Props {
  recommendations: Recommendation[];
  gamesDaysRemaining: number;
}

export default function StrategyBanner({ recommendations, gamesDaysRemaining }: Props) {
  const elites = recommendations.filter((r) => r.tier === "elite").length;
  const solids = recommendations.filter((r) => r.tier === "solid").length;
  const fillers = recommendations.filter((r) => r.tier === "filler").length;

  return (
    <div className="mx-3 bg-gray-900 border-l-[3px] border-amber-500 rounded-r-lg px-3 py-2.5">
      <div className="text-amber-500 text-xs font-bold mb-0.5">📊 STRATÉGIE</div>
      <div className="text-gray-400 text-sm">
        {elites} elites · {solids} solides · {fillers} fillers restants — ~{gamesDaysRemaining} jours de match estimés
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create RecommendationCard component**

```tsx
// web/src/components/RecommendationCard.tsx
import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

const rankColors: Record<number, string> = {
  1: "bg-green-500 text-gray-950",
  2: "bg-blue-500 text-gray-950",
  3: "bg-purple-500 text-gray-950",
};

const rankBorders: Record<number, string> = {
  1: "border-l-green-500",
  2: "border-l-blue-500",
  3: "border-l-purple-500",
};

const tierBadges: Record<string, { bg: string; text: string; label: string }> = {
  elite: { bg: "bg-green-500", text: "text-gray-950", label: "★★★ ELITE" },
  solid: { bg: "bg-blue-500", text: "text-gray-950", label: "★★ SOLIDE" },
  filler: { bg: "bg-gray-600", text: "text-gray-200", label: "★ FILLER" },
};

export default function RecommendationCard({ rec }: { rec: RecommendationWithPlayer }) {
  const { player, game, rank } = rec;
  const isHome = player.team === game.home_team;
  const opponent = isHome ? game.away_team : game.home_team;
  const tier = tierBadges[rec.tier] || tierBadges.filler;

  return (
    <Link href={`/player/${player.id}`}>
      <div
        className={`bg-gray-900 rounded-xl p-3 border-l-[3px] ${
          rankBorders[rank] || "border-l-gray-600"
        }`}
      >
        <div className="flex justify-between items-start">
          <div className="flex gap-2.5 items-center">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                rankColors[rank] || "bg-gray-600 text-gray-200"
              }`}
            >
              {rank}
            </div>
            <div>
              <div className="font-bold text-[0.95em]">{player.name}</div>
              <div className="text-gray-500 text-xs">
                {isHome ? `${player.team} vs ${opponent}` : `${player.team} @ ${opponent}`}
                {game.game_number ? ` · Game ${game.game_number}` : ""}
                {isHome ? " · 🏠 Domicile" : " · ✈️ Extérieur"}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div
              className={`font-bold text-lg ${
                rank === 1 ? "text-green-500" : rank === 2 ? "text-blue-400" : "text-purple-400"
              }`}
            >
              {rec.estimated_score.toFixed(1)}
            </div>
            <div className="text-gray-600 text-[0.65em]">score estimé</div>
          </div>
        </div>

        {/* Summary line from verdict (first sentence) */}
        <p className="text-gray-400 text-[0.78em] mt-2 leading-relaxed line-clamp-2">
          {rec.pros[0] || rec.verdict.split(".")[0]}
          {rec.cons[0] ? ` ⚠️ ${rec.cons[0]}` : ""}
        </p>

        {/* Tags */}
        <div className="flex gap-1.5 mt-2 flex-wrap">
          <span className={`${tier.bg} ${tier.text} text-[0.65em] px-2 py-0.5 rounded-full font-bold`}>
            {tier.label}
          </span>
          {rec.tags.includes("hot") && (
            <span className="bg-green-950 text-green-500 text-[0.65em] px-2 py-0.5 rounded-full">
              🔥 En forme
            </span>
          )}
          {rec.tags.includes("home") && (
            <span className="bg-blue-950 text-blue-400 text-[0.65em] px-2 py-0.5 rounded-full">
              🏠 Home
            </span>
          )}
          {rec.tags.includes("volatile") && (
            <span className="bg-red-950 text-red-400 text-[0.65em] px-2 py-0.5 rounded-full">
              🎲 Volatile
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
```

- [ ] **Step 5: Create PlayerList component (top 50)**

```tsx
// web/src/components/PlayerList.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

const tierColors: Record<string, string> = {
  elite: "text-amber-400",
  solid: "text-blue-400",
  filler: "text-gray-500",
};

export default function PlayerList({ recs }: { recs: RecommendationWithPlayer[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? recs : [];

  return (
    <div className="mx-3 mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full bg-gray-900 rounded-xl p-3 text-center text-gray-500 text-sm border border-dashed border-gray-800"
      >
        {expanded ? "▲ Replier" : `👇 Voir les ${recs.length} joueurs classés`}
      </button>

      {expanded && (
        <div className="mt-2 flex flex-col gap-1">
          {visible.map((rec) => {
            const { player, game } = rec;
            const isHome = player.team === game.home_team;
            const opponent = isHome ? game.away_team : game.home_team;

            return (
              <Link key={rec.id} href={`/player/${player.id}`}>
                <div className="bg-gray-900 rounded-lg px-3 py-2 flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 text-xs w-6 text-right">{rec.rank}</span>
                    <div>
                      <span className="font-medium text-sm">{player.name}</span>
                      <span className="text-gray-600 text-xs ml-2">
                        {player.team} {isHome ? "vs" : "@"} {opponent}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs ${tierColors[rec.tier]}`}>
                      {rec.tier === "elite" ? "★★★" : rec.tier === "solid" ? "★★" : "★"}
                    </span>
                    <span className="font-bold text-sm">{rec.estimated_score.toFixed(1)}</span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Create the home page**

```tsx
// web/src/app/page.tsx
import { supabase } from "@/lib/supabase";
import { Game, Series, Recommendation, Player, SyncLog, RecommendationWithPlayer } from "@/types";
import SyncStatus from "@/components/SyncStatus";
import GamesCollapsible from "@/components/GamesCollapsible";
import StrategyBanner from "@/components/StrategyBanner";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";

export const revalidate = 300; // ISR: revalidate every 5 minutes

async function getData() {
  const today = new Date().toISOString().split("T")[0];

  const [gamesRes, seriesRes, recsRes, playersRes, syncRes] = await Promise.all([
    supabase.from("games").select("*").eq("date", today).order("tip_off"),
    supabase.from("series").select("*").eq("status", "active"),
    supabase.from("recommendations").select("*").eq("date", today).order("rank"),
    supabase.from("players").select("*"),
    supabase.from("sync_log").select("*").order("started_at", { ascending: false }).limit(1),
  ]);

  const games = (gamesRes.data || []) as Game[];
  const series = (seriesRes.data || []) as Series[];
  const recs = (recsRes.data || []) as Recommendation[];
  const players = (playersRes.data || []) as Player[];
  const sync = (syncRes.data?.[0] || null) as SyncLog | null;

  const playersMap = new Map(players.map((p) => [p.id, p]));
  const gamesMap = new Map(games.map((g) => [g.id, g]));

  // Join recommendations with players and games
  const recsWithPlayers: RecommendationWithPlayer[] = recs
    .map((r) => {
      const player = playersMap.get(r.player_id);
      // Find the game for this player
      const game = games.find(
        (g) => g.home_team === player?.team || g.away_team === player?.team
      );
      if (!player || !game) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  // Estimate game days remaining from series
  let gameDaysRemaining = 0;
  for (const s of series) {
    const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
    const maxLeft = 7 - s.home_wins - s.away_wins;
    gameDaysRemaining += Math.round((minLeft + maxLeft) / 2);
  }
  gameDaysRemaining = Math.max(1, Math.round(gameDaysRemaining * 0.7));

  return { games, series, recsWithPlayers, sync, gameDaysRemaining };
}

export default async function TonightPage() {
  const { games, series, recsWithPlayers, sync, gameDaysRemaining } = await getData();

  const top3 = recsWithPlayers.slice(0, 3);
  const isPlayoffs = true; // TODO: detect from series/config

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center px-4 py-3 border-b border-gray-900">
        <div>
          <h1 className="text-lg font-bold">TTFL Advisor</h1>
          <p className="text-xs text-gray-500">
            {new Date().toLocaleDateString("fr-FR", {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}{" "}
            · {games.length} match{games.length > 1 ? "s" : ""} ce soir
          </p>
        </div>
        {isPlayoffs && (
          <span className="bg-gray-900 rounded-full px-2.5 py-1 text-xs text-amber-500 font-medium">
            PLAYOFFS
          </span>
        )}
      </div>

      {/* Sync status */}
      <SyncStatus sync={sync} />

      {/* Games */}
      <div className="mt-2">
        <GamesCollapsible games={games} series={series} />
      </div>

      {/* Strategy banner */}
      <div className="mt-2">
        <StrategyBanner recommendations={recsWithPlayers} gamesDaysRemaining={gameDaysRemaining} />
      </div>

      {/* Top 3 */}
      <div className="mt-4 px-3">
        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 px-1">
          Top 3 recommandations
        </h2>
        <div className="flex flex-col gap-2">
          {top3.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} />
          ))}
          {top3.length === 0 && (
            <p className="text-gray-600 text-sm text-center py-8">
              Pas encore de recommandations pour ce soir. Prochaine synchro en cours...
            </p>
          )}
        </div>
      </div>

      {/* Full list */}
      <PlayerList recs={recsWithPlayers} />
    </div>
  );
}
```

- [ ] **Step 7: Test in browser**

Run: `cd web && npm run dev`
Open http://localhost:3000 on your phone or in mobile view (Chrome DevTools).
Expected: Page renders with header, sync status, empty games/recs (until first sync runs).

- [ ] **Step 8: Commit**

```bash
cd /home/isow/workspace/perso/nba-fantasy
git add web/src/components/SyncStatus.tsx web/src/components/GamesCollapsible.tsx web/src/components/StrategyBanner.tsx web/src/components/RecommendationCard.tsx web/src/components/PlayerList.tsx web/src/app/page.tsx
git commit -m "feat: Tonight home page with top 3 recs, games collapsible, strategy banner"
```

---

## Task 12: Frontend — Player Detail Page

**Files:**
- Create: `web/src/components/ProsCons.tsx`
- Create: `web/src/app/player/[id]/page.tsx`

- [ ] **Step 1: Create ProsCons component**

```tsx
// web/src/components/ProsCons.tsx
export function ProsBlock({ pros }: { pros: string[] }) {
  return (
    <div className="bg-green-950/50 border border-green-800 rounded-xl p-3">
      <h3 className="text-green-500 font-bold text-sm mb-1.5">✅ POUR</h3>
      <ul className="text-gray-300 text-sm leading-relaxed list-disc list-inside space-y-1">
        {pros.map((p, i) => (
          <li key={i}>{p}</li>
        ))}
      </ul>
    </div>
  );
}

export function ConsBlock({ cons }: { cons: string[] }) {
  return (
    <div className="bg-red-950/50 border border-red-900 rounded-xl p-3">
      <h3 className="text-red-400 font-bold text-sm mb-1.5">❌ CONTRE</h3>
      <ul className="text-gray-300 text-sm leading-relaxed list-disc list-inside space-y-1">
        {cons.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </div>
  );
}

export function VerdictBlock({ verdict }: { verdict: string }) {
  return (
    <div className="bg-gray-900 border border-amber-800 rounded-xl p-3">
      <h3 className="text-amber-500 font-bold text-sm mb-1.5">💡 VERDICT</h3>
      <p className="text-gray-100 text-sm leading-relaxed">{verdict}</p>
    </div>
  );
}
```

- [ ] **Step 2: Create the player detail page**

```tsx
// web/src/app/player/[id]/page.tsx
import { supabase } from "@/lib/supabase";
import { Player, Recommendation, Game, Pick } from "@/types";
import { ProsBlock, ConsBlock, VerdictBlock } from "@/components/ProsCons";
import Link from "next/link";
import PickButton from "./PickButton";

export const revalidate = 300;

const tierLabels: Record<string, { label: string; color: string }> = {
  elite: { label: "★★★ Elite", color: "text-amber-400" },
  solid: { label: "★★ Solide", color: "text-blue-400" },
  filler: { label: "★ Filler", color: "text-gray-400" },
};

async function getData(playerId: number) {
  const today = new Date().toISOString().split("T")[0];

  const [playerRes, recRes, gamesRes, picksRes] = await Promise.all([
    supabase.from("players").select("*").eq("id", playerId).single(),
    supabase.from("recommendations").select("*").eq("player_id", playerId).eq("date", today).single(),
    supabase.from("games").select("*").eq("date", today),
    supabase.from("picks").select("*").eq("mode", "playoffs"),
  ]);

  const player = playerRes.data as Player | null;
  const rec = recRes.data as Recommendation | null;
  const games = (gamesRes.data || []) as Game[];
  const picks = (picksRes.data || []) as Pick[];

  const game = games.find(
    (g) => g.home_team === player?.team || g.away_team === player?.team
  );

  const alreadyPicked = picks.some((p) => p.player_id === playerId);
  const pickedToday = picks.some((p) => p.date === today);

  return { player, rec, game, alreadyPicked, pickedToday };
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const playerId = parseInt(id, 10);
  const { player, rec, game, alreadyPicked, pickedToday } = await getData(playerId);

  if (!player) {
    return <div className="p-8 text-center text-gray-500">Joueur introuvable</div>;
  }

  const isHome = game ? player.team === game.home_team : false;
  const opponent = game
    ? isHome
      ? game.away_team
      : game.home_team
    : "?";
  const tier = tierLabels[rec?.tier || "filler"];

  return (
    <div className="px-4 py-4">
      {/* Back link */}
      <Link href="/" className="text-gray-500 text-sm">
        ← Retour
      </Link>

      {/* Header */}
      <div className="flex justify-between items-start mt-3 mb-4">
        <div>
          <h1 className="text-xl font-bold">{player.name}</h1>
          <p className="text-gray-500 text-sm">
            {player.team} · {player.position}
            {game
              ? ` · ${isHome ? `vs ${opponent}` : `@ ${opponent}`}${game.game_number ? ` Game ${game.game_number}` : ""}`
              : ""}
          </p>
        </div>
        {rec && (
          <div className="text-right">
            <div className="text-green-500 font-bold text-2xl">
              {rec.estimated_score.toFixed(1)}
            </div>
            <div className="text-gray-600 text-xs">score estimé</div>
            <div className={`text-xs ${tier.color}`}>{tier.label}</div>
          </div>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">{player.avg_ttfl_l5?.toFixed(1) || "—"}</div>
          <div className="text-gray-500 text-[0.65em]">Avg TTFL L5</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">{player.avg_ttfl_season?.toFixed(1) || "—"}</div>
          <div className="text-gray-500 text-[0.65em]">Avg saison</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">
            {player.avg_ttfl_season
              ? `${Math.round(player.avg_ttfl_season - player.stddev_ttfl)} / ${Math.round(player.avg_ttfl_season + player.stddev_ttfl)}`
              : "—"}
          </div>
          <div className="text-gray-500 text-[0.65em]">Floor / Ceiling</div>
        </div>
      </div>

      {/* Pros / Cons / Verdict */}
      {rec && (
        <div className="flex flex-col gap-3 mb-4">
          <ProsBlock pros={rec.pros} />
          <ConsBlock cons={rec.cons} />
          <VerdictBlock verdict={rec.verdict} />
        </div>
      )}

      {/* Pick button */}
      {game && rec && (
        <PickButton
          playerId={player.id}
          gameId={game.id}
          playerName={player.name}
          estimatedScore={rec.estimated_score}
          alreadyPicked={alreadyPicked}
          pickedToday={pickedToday}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create PickButton client component**

```tsx
// web/src/app/player/[id]/PickButton.tsx
"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

interface Props {
  playerId: number;
  gameId: string;
  playerName: string;
  estimatedScore: number;
  alreadyPicked: boolean;
  pickedToday: boolean;
}

export default function PickButton({
  playerId,
  gameId,
  playerName,
  estimatedScore,
  alreadyPicked,
  pickedToday,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const disabled = alreadyPicked || pickedToday || done;

  const handlePick = async () => {
    if (disabled) return;
    setLoading(true);

    const today = new Date().toISOString().split("T")[0];
    const { error } = await supabase.from("picks").insert({
      player_id: playerId,
      game_id: gameId,
      date: today,
      mode: "playoffs",
      estimated_score: estimatedScore,
      picked_at: new Date().toISOString(),
    });

    setLoading(false);
    if (!error) {
      setDone(true);
    } else {
      alert(`Erreur: ${error.message}`);
    }
  };

  let label = `Picker ${playerName} ce soir`;
  let className = "w-full bg-green-600 text-gray-950 rounded-xl py-3.5 font-bold text-sm";

  if (done) {
    label = `✅ ${playerName} pické !`;
    className = "w-full bg-green-900 text-green-400 rounded-xl py-3.5 font-bold text-sm";
  } else if (alreadyPicked) {
    label = "Déjà pické en playoffs";
    className = "w-full bg-gray-800 text-gray-500 rounded-xl py-3.5 font-bold text-sm";
  } else if (pickedToday) {
    label = "Tu as déjà pické quelqu'un ce soir";
    className = "w-full bg-gray-800 text-gray-500 rounded-xl py-3.5 font-bold text-sm";
  }

  return (
    <button
      onClick={handlePick}
      disabled={disabled || loading}
      className={className}
    >
      {loading ? "..." : label}
    </button>
  );
}
```

- [ ] **Step 4: Test in browser**

Navigate to http://localhost:3000/player/203999 (or any valid player ID).
Expected: Player detail page with stats, pros/cons, verdict, and pick button.

- [ ] **Step 5: Commit**

```bash
cd /home/isow/workspace/perso/nba-fantasy
git add web/src/components/ProsCons.tsx web/src/app/player/
git commit -m "feat: player detail page with pros/cons/verdict and pick button"
```

---

## Task 13: Frontend — Picks + Strategy Pages

**Files:**
- Create: `web/src/app/picks/page.tsx`
- Create: `web/src/app/strategy/page.tsx`

- [ ] **Step 1: Create Picks page**

```tsx
// web/src/app/picks/page.tsx
import { supabase } from "@/lib/supabase";
import { Pick, Player } from "@/types";

export const revalidate = 0; // Always fresh

async function getData() {
  const [picksRes, playersRes] = await Promise.all([
    supabase.from("picks").select("*").eq("mode", "playoffs").order("date", { ascending: false }),
    supabase.from("players").select("id, name, team"),
  ]);

  const picks = (picksRes.data || []) as Pick[];
  const players = (playersRes.data || []) as Player[];
  const playersMap = new Map(players.map((p) => [p.id, p]));

  return { picks, playersMap };
}

export default async function PicksPage() {
  const { picks, playersMap } = await getData();

  const scores = picks
    .map((p) => p.actual_score)
    .filter((s): s is number => s !== null);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
  const best = scores.length ? Math.max(...scores) : 0;
  const worst = scores.length ? Math.min(...scores) : 0;

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-1">Mes picks playoffs</h1>
      <p className="text-gray-500 text-sm mb-4">
        {picks.length} joueur{picks.length > 1 ? "s" : ""} pické{picks.length > 1 ? "s" : ""}
        {scores.length > 0 ? ` · Total : ${scores.reduce((a, b) => a + b, 0)} pts TTFL` : ""}
      </p>

      {/* Stats summary */}
      {scores.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold">{avg.toFixed(1)}</div>
            <div className="text-gray-500 text-[0.65em]">Avg / pick</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold text-green-500">{best}</div>
            <div className="text-gray-500 text-[0.65em]">Meilleur</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold text-red-400">{worst}</div>
            <div className="text-gray-500 text-[0.65em]">Pire</div>
          </div>
        </div>
      )}

      {/* Pick list */}
      <div className="flex flex-col gap-2">
        {picks.map((pick) => {
          const player = playersMap.get(pick.player_id);
          const scoreColor =
            pick.actual_score === null
              ? "text-gray-500"
              : pick.actual_score >= 50
                ? "text-green-500"
                : pick.actual_score >= 30
                  ? "text-gray-100"
                  : "text-red-400";

          return (
            <div
              key={pick.id}
              className="bg-gray-900 rounded-lg px-3 py-2.5 flex justify-between items-center"
            >
              <div>
                <div className="font-bold text-sm">{player?.name || "?"}</div>
                <div className="text-gray-500 text-xs">
                  {new Date(pick.date).toLocaleDateString("fr-FR", {
                    day: "numeric",
                    month: "short",
                  })}
                  {player ? ` · ${player.team}` : ""}
                </div>
              </div>
              <div className={`font-bold ${scoreColor}`}>
                {pick.actual_score !== null ? pick.actual_score : "—"}
              </div>
            </div>
          );
        })}
        {picks.length === 0 && (
          <p className="text-gray-600 text-sm text-center py-8">
            Aucun pick encore. Va sur l'onglet "Ce soir" pour commencer !
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create Strategy page**

```tsx
// web/src/app/strategy/page.tsx
import { supabase } from "@/lib/supabase";
import { Recommendation, Series, Game } from "@/types";

export const revalidate = 300;

async function getData() {
  const today = new Date().toISOString().split("T")[0];

  // Get next 7 days of games
  const futureDate = new Date();
  futureDate.setDate(futureDate.getDate() + 7);
  const futureDateStr = futureDate.toISOString().split("T")[0];

  const [recsRes, seriesRes, gamesRes] = await Promise.all([
    supabase.from("recommendations").select("*").eq("date", today),
    supabase.from("series").select("*").eq("status", "active"),
    supabase
      .from("games")
      .select("*")
      .gte("date", today)
      .lte("date", futureDateStr)
      .order("date"),
  ]);

  const recs = (recsRes.data || []) as Recommendation[];
  const series = (seriesRes.data || []) as Series[];
  const games = (gamesRes.data || []) as Game[];

  return { recs, series, games };
}

export default async function StrategyPage() {
  const { recs, series, games } = await getData();

  const elites = recs.filter((r) => r.tier === "elite").length;
  const solids = recs.filter((r) => r.tier === "solid").length;
  const fillers = recs.filter((r) => r.tier === "filler").length;

  // Group games by date
  const gamesByDate = new Map<string, Game[]>();
  for (const g of games) {
    const list = gamesByDate.get(g.date) || [];
    list.push(g);
    gamesByDate.set(g.date, list);
  }

  // Find the date with the most games (best spot)
  let bestDate = "";
  let bestCount = 0;
  for (const [date, dateGames] of gamesByDate) {
    if (dateGames.length > bestCount) {
      bestCount = dateGames.length;
      bestDate = date;
    }
  }

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-4">Vue stratégique</h1>

      {/* Capital overview */}
      <div className="bg-gray-900 rounded-xl p-3.5 mb-3">
        <h2 className="text-amber-500 font-bold text-sm mb-2.5">Capital joueurs restant</h2>
        <div className="flex justify-around">
          <div className="text-center">
            <div className="text-amber-400 text-xl font-bold">{elites}</div>
            <div className="text-amber-400 text-xs">★★★ Elite</div>
          </div>
          <div className="text-center">
            <div className="text-blue-400 text-xl font-bold">{solids}</div>
            <div className="text-blue-400 text-xs">★★ Solide</div>
          </div>
          <div className="text-center">
            <div className="text-gray-400 text-xl font-bold">{fillers}</div>
            <div className="text-gray-400 text-xs">★ Filler</div>
          </div>
        </div>
      </div>

      {/* Upcoming week */}
      <div className="bg-gray-900 rounded-xl p-3.5 mb-3">
        <h2 className="text-purple-400 font-bold text-sm mb-2.5">Prochains 7 jours</h2>
        <div className="flex flex-col gap-1.5">
          {Array.from(gamesByDate.entries()).map(([dateStr, dateGames]) => {
            const d = new Date(dateStr + "T12:00:00");
            const dayLabel = d.toLocaleDateString("fr-FR", {
              weekday: "short",
              day: "numeric",
            });
            const isBest = dateStr === bestDate;
            const isToday = dateStr === new Date().toISOString().split("T")[0];

            return (
              <div
                key={dateStr}
                className="flex justify-between items-center text-sm py-1 border-b border-gray-950 last:border-0"
              >
                <span className={`${isToday ? "text-white font-bold" : "text-gray-400"}`}>
                  {isToday ? "Aujourd'hui" : dayLabel}
                </span>
                <span className="text-gray-100">
                  {dateGames.length} match{dateGames.length > 1 ? "s" : ""}
                </span>
                <span className={`text-xs ${isBest ? "text-amber-500" : "text-gray-600"}`}>
                  {isBest ? "⭐ Best spot semaine" : ""}
                </span>
              </div>
            );
          })}
          {gamesByDate.size === 0 && (
            <p className="text-gray-600 text-sm">Aucun match prévu</p>
          )}
        </div>
      </div>

      {/* Series tracker */}
      <div className="bg-gray-900 rounded-xl p-3.5">
        <h2 className="text-green-500 font-bold text-sm mb-2.5">Séries en cours</h2>
        <div className="flex flex-col gap-2">
          {series.map((s) => {
            const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
            const maxLeft = 7 - s.home_wins - s.away_wins;
            const estLeft = Math.round((minLeft + maxLeft) / 2);

            return (
              <div
                key={s.id}
                className="flex justify-between items-center text-sm"
              >
                <span className="text-gray-100">
                  {s.home_team} vs {s.away_team}
                </span>
                <span className="text-gray-400">
                  {s.home_wins}-{s.away_wins}
                </span>
                <span className="text-amber-500 text-xs">
                  ~{estLeft} game{estLeft > 1 ? "s" : ""} restant{estLeft > 1 ? "s" : ""}
                </span>
              </div>
            );
          })}
          {series.length === 0 && (
            <p className="text-gray-600 text-sm">Aucune série active</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Test in browser**

Navigate to http://localhost:3000/picks and http://localhost:3000/strategy.
Expected: Both pages render correctly. Empty state messages shown until data is synced.

- [ ] **Step 4: Commit**

```bash
cd /home/isow/workspace/perso/nba-fantasy
git add web/src/app/picks/page.tsx web/src/app/strategy/page.tsx
git commit -m "feat: picks history and strategy dashboard pages"
```

---

## Task 14: Deployment (Vercel + First Sync)

**Files:**
- Create: `web/.env.local` (already exists from Task 10)

- [ ] **Step 1: Add insert policy for picks (anon must write picks from frontend)**

Run this SQL in Supabase SQL Editor:

```sql
create policy "anon insert picks" on picks for insert with check (true);
```

This allows the frontend (using anon key) to insert picks. All other writes go through the service role (Python backend).

- [ ] **Step 2: Run first sync**

```bash
cd /home/isow/workspace/perso/nba-fantasy
source venv/bin/activate
python -m sync.main
```

Expected: Sync completes, data appears in Supabase tables. Check the `recommendations` table has entries for today.

- [ ] **Step 3: Deploy to Vercel**

```bash
cd /home/isow/workspace/perso/nba-fantasy/web
npx vercel
```

When prompted:
- Link to existing project or create new: create new
- Project name: ttfl-advisor
- Root directory: `./` (we're already in `web/`)

Then set environment variables:
```bash
npx vercel env add NEXT_PUBLIC_SUPABASE_URL
npx vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
```

Deploy to production:
```bash
npx vercel --prod
```

- [ ] **Step 4: Test the deployed PWA**

1. Open the Vercel URL on your phone
2. Verify the home page loads with tonight's recommendations
3. Tap a player → verify detail page with pros/cons/verdict
4. Install as PWA (Add to Home Screen)
5. Verify picks and strategy pages work

- [ ] **Step 5: Set up crontab**

```bash
crontab -e
```

Add:
```cron
0 7 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 12 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 17 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 22 * * * cd /home/isow/workspace/perso/nba-fantasy && /home/isow/workspace/perso/nba-fantasy/venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
```

- [ ] **Step 6: Final commit and push**

```bash
cd /home/isow/workspace/perso/nba-fantasy
git add -A
git commit -m "feat: deployment configuration and crontab setup"
git push origin main
```
