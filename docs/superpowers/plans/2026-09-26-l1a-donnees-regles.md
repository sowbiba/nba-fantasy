# L1a — Données et règles : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser la couche de règles TTFL (R1-R15) en Python pur et en SQL, avec un modèle de données cloisonné par saison et une disponibilité des joueurs vérifiée en base, sans toucher au sync existant.

**Architecture:** Nouveau package `engine/rules/` en Python pur, sans Supabase, testé par des fichiers de cas JSON. Les mêmes cas JSON sont rejoués contre les fonctions SQL des migrations 017-019, sur un Postgres jetable (Docker en local, service en CI). Les colonnes dérivées (`game_type`, `season`, `game_logs.team`) sont remplies par des triggers : le sync actuel n'a rien à changer.

**Tech Stack:** Python 3.14, pytest, psycopg 3 (tests SQL uniquement), PostgreSQL 17 (Supabase), `zoneinfo`.

**Spec:** `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md`, avec `docs/regles-ttfl.md` (R1-R15) comme spécification des règles.

## Global Constraints

- Cooldown SR : un joueur pické le jour J est disponible à **J+30** (`COOLDOWN_DAYS = 30`), dans les deux sens autour de chaque pick, réservations comprises (R3).
- Seconde chance : débloque le pick à 0 visé, du jour d'achat jusqu'à **achat + 7 jours** inclus (R15).
- Soirées éligibles : `regular`, `cup_final`, `playoffs`. Exclus : `preseason`, `playin`, `allstar`, `unknown` (R11, R12).
- Mode d'une soirée : `playoffs` si le match est `playoffs`, sinon `regular`. Jamais saisi à la main.
- Date d'une soirée = date US du match (`games.date`).
- Fermeture (R8) = min(00:00 Europe/Paris du lendemain de la soirée, premier tip-off de la soirée).
- Migrations 017+ **idempotentes** : `if not exists`, `create or replace`, `drop ... if exists` avant chaque `create policy` / `create trigger`.
- `engine/rules/` n'importe **rien** de `sync/` ni de Supabase.
- Les implémentations Python et SQL d'une même règle sont vérifiées par **le même fichier de cas JSON**.
- Aucune écriture en prod sans le feu vert explicite de l'utilisateur (tâche 9).

## Review Focus

- **Pick sur un match inéligible ou inconnu** (présaison, play-in, `unknown_*`) : refus explicite `night_not_eligible`, jamais d'acceptation silencieuse. Test : tâche 6, `test_trigger_refuse_match_ineligible`.
- **Remplacement d'un joueur à date égale** (R2, `UPDATE picks set player_id`) : autorisé si le nouveau joueur est disponible, sans que la ligne remplacée se bloque elle-même. Test : tâche 6, `test_trigger_remplacement_meme_date`.
- **Mise à jour du score d'un pick existant par le sync** (`actual_score`, `is_x2`) : ne déclenche jamais la validation, même si l'historique importé est incohérent. Test : tâche 6, `test_trigger_ignore_maj_score`.
- **Soirée sans match éligible** (week-end All-Star, jours de play-in) : aucune ligne dans `nights`, donc pas de soirée TTFL. Test : tâche 7, `test_build_nights_ignore_soiree_sans_match_eligible`.
- **Nuits de changement d'heure** (25/10/2026, 28/03/2027) : fermeture à minuit heure de Paris avec le bon décalage UTC. Test : tâche 7, `test_closing_at_changement_heure_hiver` et `test_closing_at_changement_heure_ete`.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `engine/__init__.py`, `engine/rules/__init__.py` | Package moteur, couche règles |
| `engine/rules/game_types.py` | R11/R12 : type et saison d'un match depuis son identifiant |
| `engine/rules/scoring.py` | R1 (formule TTFL), R10 (x2), R14 (moyenne sur soirées éligibles) |
| `engine/rules/availability.py` | R3, R4, R5, R6, R15 : disponibilité d'un joueur pour une soirée |
| `engine/rules/calendar.py` | R8 (fermeture), R13 (match fantôme), construction des soirées |
| `supabase/migrations/002…013` | Ajout de `drop policy if exists` avant chaque `create policy` (rejouabilité) |
| `supabase/migrations/017_season_game_type.sql` | Saison, type de match, `game_logs.team`, colonnes non déclarées, `players.active` |
| `supabase/migrations/018_picks_availability.sql` | `picks.season`/`is_x2`, `second_chances`, `player_available_on`, trigger de validation, backfills |
| `supabase/migrations/019_nights_plan.sql` | Tables `nights` et `plan`, fonction `player_availability(night)` |
| `sync/ttfl.py` | Délègue la formule à `engine.rules.scoring` (seule retouche de `sync/`) |
| `tests/rules/*.py`, `tests/rules/*_cases.json` | Tests Python des règles et cas partagés |
| `tests/sql/conftest.py`, `tests/sql/*.py` | Postgres jetable, rejeu des cas JSON contre le SQL |
| `requirements-dev.txt` | Dépendances de test (`psycopg[binary]`) |
| `.github/workflows/ci.yml` | Service Postgres pour les tests SQL |
| `docs/operations.md` | Lancer les tests SQL en local |

---

### Task 1: Harnais de tests SQL et migrations rejouables

**Files:**
- Create: `requirements-dev.txt`, `tests/sql/__init__.py`, `tests/sql/conftest.py`, `tests/sql/test_migrations.py`
- Modify: `supabase/migrations/002_weekly_plan.sql`, `004_picks_delete.sql`, `005_player_watchlist.sql`, `006_series_forecast.sql`, `011_matchup_aggregates_rls.sql`, `012_team_outlook_player_ranks.sql`, `013_box_score_matchups_raw.sql`
- Modify: `.github/workflows/ci.yml`, `docs/operations.md`

**Interfaces:**
- Produces: fixture pytest `pg` (connexion psycopg `autocommit=True` sur une base reconstruite depuis `schema.sql` et toutes les migrations) ; constantes `SQL_DIR`, `MIGRATIONS` dans `tests/sql/conftest.py`. Les tests SQL font `pytest.skip` si `TEST_DATABASE_URL` est absent.

- [ ] **Step 1: Ajouter les dépendances de test**

`requirements-dev.txt` :

```
-r requirements.txt
psycopg[binary]>=3.2
```

Run: `./venv/bin/python -m pip install -r requirements-dev.txt` (ou `uv pip install --python venv -r requirements-dev.txt`)
Expected: `Successfully installed psycopg…`

- [ ] **Step 2: Démarrer un Postgres jetable en local**

```bash
docker run -d --rm --name ttfl-pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:17
```

Puis, dans le shell des tests : `export TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres`

- [ ] **Step 3: Écrire le harnais et le test de reconstruction**

`tests/sql/__init__.py` : fichier vide.

`tests/sql/conftest.py` :

```python
"""Postgres jetable pour tester le SQL des migrations.

La base est reconstruite de zéro (schema.sql puis chaque migration dans
l'ordre des fichiers), exactement comme le décrit l'en-tête de schema.sql.
Ignoré si TEST_DATABASE_URL n'est pas défini.
"""
import os
import pathlib

import pytest

psycopg = pytest.importorskip("psycopg")

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "supabase"
MIGRATIONS = sorted((SQL_DIR / "migrations").glob("*.sql"))


def apply_migrations(conn) -> None:
    for path in MIGRATIONS:
        conn.execute(path.read_text())


@pytest.fixture(scope="session")
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL non défini (voir docs/operations.md, « Tests SQL »)")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade; create schema public;")
        conn.execute((SQL_DIR / "schema.sql").read_text())
        apply_migrations(conn)
        yield conn
```

`tests/sql/test_migrations.py` :

```python
from tests.sql.conftest import apply_migrations


def test_migrations_rejouables(pg):
    # Une base déjà à jour doit accepter un second passage complet sans erreur.
    apply_migrations(pg)
```

- [ ] **Step 4: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/sql/test_migrations.py -v`
Expected: ERROR lors de la construction de la fixture : `psycopg.errors.DuplicateObject: policy "anon read weekly_plan" for table "weekly_plan" already exists`

- [ ] **Step 5: Rendre chaque `create policy` rejouable**

Script ponctuel, à lancer une fois depuis la racine, puis relire le diff :

```bash
./venv/bin/python - <<'EOF'
import pathlib, re
pat = re.compile(r'create policy\s+("[^"]+")\s+on\s+([a-z_]+)', re.I)
for f in sorted(pathlib.Path("supabase/migrations").glob("0*.sql")):
    src = f.read_text()
    out = pat.sub(lambda m: f"drop policy if exists {m.group(1)} on {m.group(2)};\ncreate policy {m.group(1)} on {m.group(2)}", src)
    if out != src:
        f.write_text(out)
        print("modifié :", f.name)
EOF
git diff --stat supabase/migrations
```

Expected: `002`, `004`, `005`, `006`, `011`, `012`, `013` modifiés. Chaque `create policy "X" on T` est désormais précédé de `drop policy if exists "X" on T;`. Aucun changement pour la prod, où ces migrations ne seront pas rejouées.

- [ ] **Step 6: Relancer le test**

Run: `./venv/bin/python -m pytest tests/sql/test_migrations.py -v`
Expected: PASS

- [ ] **Step 7: Ajouter Postgres à la CI**

Dans `.github/workflows/ci.yml`, remplacer le job `tests` par :

```yaml
jobs:
  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: pg
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest tests/ -v
        env:
          # sync/config.py reads these at import; the tests never hit Supabase
          SUPABASE_URL: http://localhost
          SUPABASE_KEY: test
          SUPABASE_SERVICE_KEY: test
          TEST_DATABASE_URL: postgresql://postgres:pg@localhost:5432/postgres
```

- [ ] **Step 8: Documenter les tests SQL**

Ajouter à la fin de `docs/operations.md` :

````markdown
## Tests SQL

Les fonctions et triggers SQL (migrations 017+) sont testés sur un Postgres jetable, reconstruit à chaque session de tests depuis `schema.sql` et toutes les migrations.

```bash
docker run -d --rm --name ttfl-pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -v
docker stop ttfl-pg
```

Sans `TEST_DATABASE_URL`, ces tests sont ignorés. En CI, un service Postgres les fait tourner à chaque push.
````

- [ ] **Step 9: Vérifier la suite complète et commiter**

Run: `./venv/bin/python -m pytest -q`
Expected: tous les tests passent (97 existants + 1).

```bash
git add requirements-dev.txt tests/sql supabase/migrations .github/workflows/ci.yml docs/operations.md
git commit -m "test: harnais Postgres jetable et migrations rejouables"
```

---

### Task 2: Types de match et saisons (R11, R12) en Python

**Files:**
- Create: `engine/__init__.py`, `engine/rules/__init__.py`, `engine/rules/game_types.py`
- Create: `tests/rules/__init__.py`, `tests/rules/game_type_cases.json`, `tests/rules/test_game_types.py`

**Interfaces:**
- Produces:
  - `game_type_of(game_id: str) -> str` : `'preseason' | 'regular' | 'allstar' | 'playoffs' | 'playin' | 'cup_final' | 'unknown'`
  - `season_of(game_id: str, game_date: date) -> str` : `'2025-26'`
  - `is_eligible(game_type: str) -> bool`
  - `mode_of(game_type: str) -> str` : `'regular' | 'playoffs'`
  - `ELIGIBLE_TYPES: frozenset[str]`
  - Fichier `tests/rules/game_type_cases.json` : `[{"id", "date", "game_type", "season"}]`, rejoué contre le SQL en tâche 3.

- [ ] **Step 1: Écrire les cas partagés**

`tests/rules/game_type_cases.json` :

```json
[
  {"id": "0022500001", "date": "2025-10-21", "game_type": "regular", "season": "2025-26"},
  {"id": "0022600001", "date": "2026-10-20", "game_type": "regular", "season": "2026-27"},
  {"id": "0012600001", "date": "2026-10-05", "game_type": "preseason", "season": "2026-27"},
  {"id": "0032500001", "date": "2026-02-15", "game_type": "allstar", "season": "2025-26"},
  {"id": "0042500101", "date": "2026-04-18", "game_type": "playoffs", "season": "2025-26"},
  {"id": "0052500101", "date": "2026-04-14", "game_type": "playin", "season": "2025-26"},
  {"id": "0062500001", "date": "2025-12-16", "game_type": "cup_final", "season": "2025-26"},
  {"id": "hist_2025-10-25", "date": "2025-10-25", "game_type": "regular", "season": "2025-26"},
  {"id": "hist_2026-04-06", "date": "2026-04-06", "game_type": "regular", "season": "2025-26"},
  {"id": "unknown_1628983_2026-01-01", "date": "2026-01-01", "game_type": "unknown", "season": "2025-26"},
  {"id": "0072600001", "date": "2026-11-01", "game_type": "unknown", "season": "2026-27"}
]
```

Note : le préfixe `006` de la finale NBA Cup n'est pas encore vérifié, faute de finale 2025 en base. La tâche 9 le contrôle sur le calendrier 2026-27.

- [ ] **Step 2: Écrire le test**

`engine/__init__.py`, `engine/rules/__init__.py`, `tests/rules/__init__.py` : fichiers vides.

`tests/rules/test_game_types.py` :

```python
import json
import pathlib
from datetime import date

import pytest

from engine.rules.game_types import game_type_of, is_eligible, mode_of, season_of

CASES = json.loads((pathlib.Path(__file__).parent / "game_type_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_type_et_saison(case):
    d = date.fromisoformat(case["date"])
    assert game_type_of(case["id"]) == case["game_type"]
    assert season_of(case["id"], d) == case["season"]


@pytest.mark.parametrize("game_type,eligible", [
    ("regular", True), ("cup_final", True), ("playoffs", True),
    ("preseason", False), ("playin", False), ("allstar", False), ("unknown", False),
])
def test_eligibilite(game_type, eligible):
    assert is_eligible(game_type) is eligible


def test_mode():
    assert mode_of("playoffs") == "playoffs"
    assert mode_of("regular") == "regular"
    assert mode_of("cup_final") == "regular"
```

- [ ] **Step 3: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/rules/test_game_types.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.rules.game_types'`

- [ ] **Step 4: Implémenter**

`engine/rules/game_types.py` :

```python
"""R11 / R12 — type et saison d'un match NBA, déduits de son identifiant.

Identifiants NBA : 3 chiffres de type + 2 chiffres d'année de début de saison
(« 0022500001 » = saison régulière 2025-26). Les matchs `hist_<date>` sont
les supports des picks 2025-26 importés : saison régulière, saison déduite
de la date. Miroir SQL : game_type_of / season_of (migration 017).
"""
from datetime import date

_PREFIX_TYPES = {
    "001": "preseason",
    "002": "regular",
    "003": "allstar",
    "004": "playoffs",
    "005": "playin",
    "006": "cup_final",
}

ELIGIBLE_TYPES = frozenset({"regular", "cup_final", "playoffs"})


def game_type_of(game_id: str) -> str:
    if game_id.startswith("hist_"):
        return "regular"
    return _PREFIX_TYPES.get(game_id[:3], "unknown")


def _season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_of(game_id: str, game_date: date) -> str:
    if game_id[:3] in _PREFIX_TYPES and game_id[3:5].isdigit():
        return _season_label(2000 + int(game_id[3:5]))
    start = game_date.year if game_date.month >= 9 else game_date.year - 1
    return _season_label(start)


def is_eligible(game_type: str) -> bool:
    return game_type in ELIGIBLE_TYPES


def mode_of(game_type: str) -> str:
    return "playoffs" if game_type == "playoffs" else "regular"
```

- [ ] **Step 5: Relancer le test**

Run: `./venv/bin/python -m pytest tests/rules/test_game_types.py -v`
Expected: PASS (19 tests)

- [ ] **Step 6: Commiter**

```bash
git add engine tests/rules
git commit -m "feat(rules): type et saison des matchs (R11, R12)"
```

---

### Task 3: Migration 017 : saisons, types de match, équipe au moment du match

**Files:**
- Create: `supabase/migrations/017_season_game_type.sql`
- Create: `tests/sql/test_017_season_game_type.py`

**Interfaces:**
- Consumes: `tests/rules/game_type_cases.json` (tâche 2), fixture `pg` (tâche 1).
- Produces:
  - fonctions SQL `game_type_of(text) -> text`, `season_of(text, date) -> text` ;
  - colonnes `games.game_type`, `games.season`, `game_logs.team`, `game_logs.season`, `series.season`, `players.active` ;
  - triggers `games_fill_type` et `game_logs_fill`, qui remplissent ces colonnes à chaque écriture.

- [ ] **Step 1: Écrire le test**

`tests/sql/test_017_season_game_type.py` :

```python
import json
import pathlib

import pytest

CASES = json.loads(
    (pathlib.Path(__file__).parents[1] / "rules" / "game_type_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_game_type_sql_identique_au_python(pg, case):
    row = pg.execute(
        "select game_type_of(%s), season_of(%s, %s::date)",
        (case["id"], case["id"], case["date"]),
    ).fetchone()
    assert row == (case["game_type"], case["season"])


def test_trigger_games_remplit_type_et_saison(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into games (id, date, home_team, away_team) "
            "values ('0012600007', '2026-10-05', 'DEN', 'LAL')"
        )
        row = pg.execute(
            "select game_type, season from games where id = '0012600007'"
        ).fetchone()
        assert row == ("preseason", "2026-27")


def test_trigger_game_logs_equipe_au_moment_du_match(pg):
    # Joueur transféré depuis : game_logs.team garde l'équipe du match,
    # pas l'équipe actuelle de players.team.
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'X', 'BOS', 'G')")
        pg.execute(
            "insert into games (id, date, home_team, away_team) "
            "values ('0022500050', '2025-11-01', 'DEN', 'LAL')"
        )
        pg.execute(
            "insert into game_logs (player_id, game_id, date, is_home) "
            "values (1, '0022500050', '2025-11-01', false)"
        )
        row = pg.execute(
            "select team, season from game_logs where game_id = '0022500050'"
        ).fetchone()
        assert row == ("LAL", "2025-26")


def test_colonnes_prod_declarees(pg):
    cols = {
        (t, c)
        for t, c in pg.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public'"
        ).fetchall()
    }
    for expected in [
        ("games", "home_score"), ("games", "away_score"),
        ("players", "injury_short_comment"), ("players", "injury_return_date"),
        ("players", "injury_updated_at"), ("players", "active"),
        ("series", "season"),
    ]:
        assert expected in cols
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/sql/test_017_season_game_type.py -v`
Expected: FAIL avec `psycopg.errors.UndefinedFunction: function game_type_of(unknown) does not exist`

- [ ] **Step 3: Écrire la migration**

`supabase/migrations/017_season_game_type.sql` :

```sql
-- 017 — Saison et type de match (R11/R12), équipe du joueur au moment du
-- match, et colonnes présentes en prod mais jamais déclarées (audit §5).
-- Idempotente. Les colonnes dérivées sont remplies par trigger : le sync
-- n'a rien à calculer.

-- Dérive de schéma : colonnes écrites par le sync, absentes des fichiers SQL.
alter table games add column if not exists home_score integer;
alter table games add column if not exists away_score integer;
alter table players add column if not exists injury_short_comment text;
alter table players add column if not exists injury_return_date text;
alter table players add column if not exists injury_updated_at text;

-- Joueur présent dans un effectif actuel (false = coupé / hors NBA).
alter table players add column if not exists active boolean not null default true;

-- Miroir de engine/rules/game_types.py (mêmes cas : tests/rules/game_type_cases.json).
create or replace function game_type_of(p_id text) returns text
language sql immutable as $$
  select case
    when p_id like 'hist\_%' then 'regular'
    when left(p_id, 3) = '001' then 'preseason'
    when left(p_id, 3) = '002' then 'regular'
    when left(p_id, 3) = '003' then 'allstar'
    when left(p_id, 3) = '004' then 'playoffs'
    when left(p_id, 3) = '005' then 'playin'
    when left(p_id, 3) = '006' then 'cup_final'
    else 'unknown'
  end
$$;

create or replace function season_of(p_id text, p_date date) returns text
language sql immutable as $$
  select y::text || '-' || lpad(((y + 1) % 100)::text, 2, '0')
  from (
    select case
      when p_id ~ '^00[1-6][0-9]{2}' then 2000 + substr(p_id, 4, 2)::int
      when extract(month from p_date) >= 9 then extract(year from p_date)::int
      else extract(year from p_date)::int - 1
    end as y
  ) s
$$;

alter table games add column if not exists game_type text;
alter table games add column if not exists season text;
update games set game_type = game_type_of(id), season = season_of(id, date)
where game_type is null or season is null;
create index if not exists idx_games_season_type on games(season, game_type);

create or replace function games_fill_type() returns trigger
language plpgsql as $$
begin
  new.game_type := game_type_of(new.id);
  new.season := season_of(new.id, new.date);
  return new;
end
$$;
drop trigger if exists games_fill_type on games;
create trigger games_fill_type before insert or update of id, date on games
  for each row execute function games_fill_type();

-- Équipe du joueur au moment du match (corrige l'attribution de
-- compute_team_defense après transferts) et saison du log.
alter table game_logs add column if not exists team text;
alter table game_logs add column if not exists season text;
update game_logs gl
set team = coalesce(gl.team, case when gl.is_home then g.home_team else g.away_team end),
    season = coalesce(gl.season, g.season)
from games g
where g.id = gl.game_id and (gl.team is null or gl.season is null);
create index if not exists idx_game_logs_season_team on game_logs(season, team);

create or replace function game_logs_fill() returns trigger
language plpgsql as $$
declare
  v_team text;
  v_season text;
begin
  if new.team is null or new.season is null then
    select case when new.is_home then g.home_team else g.away_team end, g.season
      into v_team, v_season
      from games g where g.id = new.game_id;
    new.team := coalesce(new.team, v_team);
    new.season := coalesce(new.season, v_season);
  end if;
  return new;
end
$$;
drop trigger if exists game_logs_fill on game_logs;
create trigger game_logs_fill before insert or update of game_id, is_home on game_logs
  for each row execute function game_logs_fill();

-- Séries rattachées à leur saison : une affiche de 2027 ne doit plus
-- retomber sur la série « completed » de 2026 (audit §2).
alter table series add column if not exists season text;
update series s set season = sub.season
from (select series_id, min(season) as season from games
      where series_id is not null group by series_id) sub
where sub.series_id = s.id and s.season is null;
-- Séries non rattachées à un match : les seules existantes sont les PO 2026.
update series set season = '2025-26' where season is null;
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/sql -v`
Expected: PASS (dont `test_migrations_rejouables`, qui vérifie aussi que la 017 est rejouable)

- [ ] **Step 5: Commiter**

```bash
git add supabase/migrations/017_season_game_type.sql tests/sql/test_017_season_game_type.py
git commit -m "feat(db): saison, type de match et équipe au moment du match (017)"
```

---

### Task 4: Score TTFL, x2 et moyenne (R1, R10, R14)

**Files:**
- Create: `engine/rules/scoring.py`, `tests/rules/test_scoring_rules.py`
- Modify: `sync/ttfl.py`

**Interfaces:**
- Produces:
  - `compute_ttfl_score(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov) -> int` (signature identique à `sync.ttfl`) ;
  - `night_points(actual_score: int | None, is_x2: bool) -> int | None` ;
  - `period_average(eligible_nights: list[date], results: dict[date, tuple[int | None, bool]]) -> float | None`.

- [ ] **Step 1: Écrire le test**

`tests/rules/test_scoring_rules.py` :

```python
from datetime import date

from engine.rules.scoring import compute_ttfl_score, night_points, period_average


def test_formule_exemple_officiel():
    # Exemple de la FAQ : 28 pts, 10 reb, 6 ast, 2 stl, 1 blk, 11/20, 3/7 à 3pts, 3/4 LF, 4 BP → 41
    assert compute_ttfl_score(
        pts=28, reb=10, ast=6, stl=2, blk=1, fgm=11, fga=20,
        tpm=3, tpa=7, ftm=3, fta=4, tov=4,
    ) == 41


def test_x2_double_le_score():
    assert night_points(53, is_x2=True) == 106


def test_x2_double_aussi_un_score_negatif():
    assert night_points(-7, is_x2=True) == -14


def test_x2_sur_un_zero_reste_zero():
    assert night_points(0, is_x2=True) == 0


def test_pick_pas_encore_score():
    assert night_points(None, is_x2=False) is None


def test_moyenne_compte_les_soirees_sans_pick_pour_zero():
    nights = [date(2025, 11, 1), date(2025, 11, 2), date(2025, 11, 3)]
    results = {date(2025, 11, 1): (40, False), date(2025, 11, 2): (20, True)}
    # (40 + 40 + 0) / 3 soirées éligibles, la 3e sans pick compte 0 (R14)
    assert period_average(nights, results) == 80 / 3


def test_moyenne_ignore_les_picks_pas_encore_scores():
    nights = [date(2025, 11, 1), date(2025, 11, 2)]
    results = {date(2025, 11, 1): (30, False), date(2025, 11, 2): (None, False)}
    assert period_average(nights, results) == 30.0


def test_moyenne_sans_soiree():
    assert period_average([], {}) is None
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/rules/test_scoring_rules.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.rules.scoring'`

- [ ] **Step 3: Implémenter**

`engine/rules/scoring.py` :

```python
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
```

- [ ] **Step 4: Faire déléguer `sync/ttfl.py`**

Remplacer `compute_ttfl_score` dans `sync/ttfl.py` par l'import (la docstring de module et `compute_ttfl_from_game_log` restent inchangées) :

```python
"""TTFL score calculator.

Formula: (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM)
       - (TOV + FG_miss + 3P_miss + FT_miss)
"""
from engine.rules.scoring import compute_ttfl_score  # R1, source unique


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

- [ ] **Step 5: Lancer toute la suite**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS, y compris `tests/test_ttfl.py` inchangé.

- [ ] **Step 6: Commiter**

```bash
git add engine/rules/scoring.py tests/rules/test_scoring_rules.py sync/ttfl.py
git commit -m "feat(rules): score TTFL, x2 et moyenne sur soirées éligibles (R1, R10, R14)"
```

---

### Task 5: Disponibilité d'un joueur (R3, R4, R5, R6, R15) en Python

**Files:**
- Create: `engine/rules/availability.py`, `tests/rules/availability_cases.json`, `tests/rules/test_availability.py`

**Interfaces:**
- Produces:
  - `COOLDOWN_DAYS = 30`, `SECOND_CHANCE_DAYS = 7` ;
  - dataclasses `PickRow(id, player_id, date, mode, season)`, `SecondChance(pick_id, player_id, bought_on, expires_on)`, `SeriesRow(season, round, home_team, away_team, home_wins, away_wins, status)`, `Availability(ok, available_from=None, reason=None)` ;
  - `is_available(*, player_id, player_team, night, season, mode, picks, second_chances=(), series=(), exclude_pick_id=None) -> Availability` ;
  - motifs `reason` : `'cooldown'` (avec `available_from`), `'reserved_nearby'`, `'playoffs_used'`, `'not_qualified'`, `'team_eliminated'` ;
  - fichier `tests/rules/availability_cases.json`, rejoué contre le SQL en tâche 6.

- [ ] **Step 1: Écrire les cas partagés**

`tests/rules/availability_cases.json` :

```json
[
  {"name": "sr_aucun_pick", "night": "2025-11-24", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN", "picks": [], "second_chances": [], "series": [],
   "exclude_pick_id": null, "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_j29_bloque", "night": "2025-11-23", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 1, "player_id": 1, "date": "2025-10-25", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": "2025-11-24", "reason": "cooldown"}},

  {"name": "sr_j30_ok_cas_reel_jokic", "night": "2025-11-24", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 1, "player_id": 1, "date": "2025-10-25", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_deux_picks_anterieurs_prend_le_plus_recent", "night": "2025-12-10", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 1, "player_id": 1, "date": "2025-10-25", "mode": "regular", "season": "2025-26"},
             {"id": 2, "player_id": 1, "date": "2025-11-24", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": "2025-12-24", "reason": "cooldown"}},

  {"name": "sr_reservation_future_bloque", "night": "2025-11-20", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 5, "player_id": 1, "date": "2025-12-10", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": null, "reason": "reserved_nearby"}},

  {"name": "sr_reservation_future_a_30_jours_ok", "night": "2025-11-20", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 5, "player_id": 1, "date": "2025-12-20", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_remplacement_meme_date_s_exclut", "night": "2025-11-20", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 7, "player_id": 1, "date": "2025-11-20", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": 7,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_pick_d_un_autre_joueur_ignore", "night": "2025-11-20", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "DEN",
   "picks": [{"id": 8, "player_id": 2, "date": "2025-11-10", "mode": "regular", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_seconde_chance_active_cas_reel_mobley", "night": "2025-11-21", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "CLE",
   "picks": [{"id": 3, "player_id": 1, "date": "2025-11-12", "mode": "regular", "season": "2025-26"}],
   "second_chances": [{"pick_id": 3, "player_id": 1, "bought_on": "2025-11-17", "expires_on": "2025-11-24"}],
   "series": [], "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "sr_seconde_chance_expiree", "night": "2025-11-26", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "CLE",
   "picks": [{"id": 3, "player_id": 1, "date": "2025-11-12", "mode": "regular", "season": "2025-26"}],
   "second_chances": [{"pick_id": 3, "player_id": 1, "bought_on": "2025-11-17", "expires_on": "2025-11-24"}],
   "series": [], "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": "2025-12-12", "reason": "cooldown"}},

  {"name": "sr_seconde_chance_pas_encore_achetee", "night": "2025-11-15", "season": "2025-26", "mode": "regular",
   "player_id": 1, "player_team": "CLE",
   "picks": [{"id": 3, "player_id": 1, "date": "2025-11-12", "mode": "regular", "season": "2025-26"}],
   "second_chances": [{"pick_id": 3, "player_id": 1, "bought_on": "2025-11-17", "expires_on": "2025-11-24"}],
   "series": [], "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": "2025-12-12", "reason": "cooldown"}},

  {"name": "sr_nouvelle_saison_ignore_les_picks_po_precedents", "night": "2026-10-25", "season": "2026-27", "mode": "regular",
   "player_id": 1, "player_team": "NYK",
   "picks": [{"id": 9, "player_id": 1, "date": "2026-06-05", "mode": "playoffs", "season": "2025-26"}],
   "second_chances": [], "series": [], "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "po_picks_sr_ignores_remise_a_zero", "night": "2026-04-20", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "NYK",
   "picks": [{"id": 10, "player_id": 1, "date": "2026-04-10", "mode": "regular", "season": "2025-26"}],
   "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 1, "away_wins": 0, "status": "active"}],
   "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "po_deja_utilise", "night": "2026-05-20", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "NYK",
   "picks": [{"id": 11, "player_id": 1, "date": "2026-04-19", "mode": "playoffs", "season": "2025-26"}],
   "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 4, "away_wins": 1, "status": "completed"}],
   "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": null, "reason": "playoffs_used"}},

  {"name": "po_remplacement_meme_date_s_exclut", "night": "2026-04-19", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "NYK",
   "picks": [{"id": 11, "player_id": 1, "date": "2026-04-19", "mode": "playoffs", "season": "2025-26"}],
   "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 0, "away_wins": 0, "status": "active"}],
   "exclude_pick_id": 11,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "po_equipe_eliminee", "night": "2026-05-06", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "ATL", "picks": [], "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 4, "away_wins": 1, "status": "completed"}],
   "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": null, "reason": "team_eliminated"}},

  {"name": "po_vainqueur_de_serie_ok", "night": "2026-05-06", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "NYK", "picks": [], "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 4, "away_wins": 1, "status": "completed"}],
   "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}},

  {"name": "po_equipe_eliminee_au_play_in", "night": "2026-04-20", "season": "2025-26", "mode": "playoffs",
   "player_id": 1, "player_team": "CHI", "picks": [], "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 1, "away_wins": 0, "status": "active"}],
   "exclude_pick_id": null,
   "expected": {"ok": false, "available_from": null, "reason": "not_qualified"}},

  {"name": "po_series_d_une_autre_saison_ignorees", "night": "2027-04-20", "season": "2026-27", "mode": "playoffs",
   "player_id": 1, "player_team": "ATL", "picks": [], "second_chances": [],
   "series": [{"season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL", "home_wins": 4, "away_wins": 1, "status": "completed"},
              {"season": "2026-27", "round": 1, "home_team": "ATL", "away_team": "BOS", "home_wins": 0, "away_wins": 0, "status": "active"}],
   "exclude_pick_id": null,
   "expected": {"ok": true, "available_from": null, "reason": null}}
]
```

- [ ] **Step 2: Écrire le test**

`tests/rules/test_availability.py` :

```python
import json
import pathlib
from datetime import date

import pytest

from engine.rules.availability import (
    Availability, PickRow, SecondChance, SeriesRow, is_available,
)

CASES = json.loads((pathlib.Path(__file__).parent / "availability_cases.json").read_text())


def _d(s):
    return date.fromisoformat(s) if s else None


def run_case(case) -> Availability:
    return is_available(
        player_id=case["player_id"],
        player_team=case["player_team"],
        night=_d(case["night"]),
        season=case["season"],
        mode=case["mode"],
        picks=[PickRow(p["id"], p["player_id"], _d(p["date"]), p["mode"], p["season"]) for p in case["picks"]],
        second_chances=[
            SecondChance(s["pick_id"], s["player_id"], _d(s["bought_on"]), _d(s["expires_on"]))
            for s in case["second_chances"]
        ],
        series=[SeriesRow(**s) for s in case["series"]],
        exclude_pick_id=case["exclude_pick_id"],
    )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_disponibilite(case):
    exp = case["expected"]
    assert run_case(case) == Availability(exp["ok"], _d(exp["available_from"]), exp["reason"])
```

- [ ] **Step 3: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/rules/test_availability.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.rules.availability'`

- [ ] **Step 4: Implémenter**

`engine/rules/availability.py` :

```python
"""R3, R4, R5, R6, R15 — disponibilité d'un joueur pour une soirée.

Miroir exact de la fonction SQL player_available_on (migration 018) : les
deux implémentations rejouent tests/rules/availability_cases.json.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

COOLDOWN_DAYS = 30       # R3 : pické le jour J → disponible à J+30
SECOND_CHANCE_DAYS = 7   # R15 : repick dans les 7 jours suivant l'achat


@dataclass(frozen=True)
class PickRow:
    id: int
    player_id: int
    date: date
    mode: str    # 'regular' | 'playoffs'
    season: str


@dataclass(frozen=True)
class SecondChance:
    pick_id: int   # le pick à 0 que le bonus débloque
    player_id: int
    bought_on: date
    expires_on: date


@dataclass(frozen=True)
class SeriesRow:
    season: str
    round: int
    home_team: str
    away_team: str
    home_wins: int
    away_wins: int
    status: str


@dataclass(frozen=True)
class Availability:
    ok: bool
    available_from: date | None = None
    reason: str | None = None


AVAILABLE = Availability(True)


def is_available(
    *,
    player_id: int,
    player_team: str,
    night: date,
    season: str,
    mode: str,
    picks: Iterable[PickRow],
    second_chances: Iterable[SecondChance] = (),
    series: Iterable[SeriesRow] = (),
    exclude_pick_id: int | None = None,
) -> Availability:
    """Le joueur peut-il être pické (ou réservé) pour `night` ?

    Seuls comptent les picks du joueur dans la même saison et le même mode
    (R6 : les picks de SR ne comptent plus en PO). `exclude_pick_id` écarte
    la ligne en cours de remplacement (R2).
    """
    own = [
        p for p in picks
        if p.player_id == player_id and p.season == season
        and p.mode == mode and p.id != exclude_pick_id
    ]
    if mode == "playoffs":
        return _playoffs(own, player_team, season, list(series))
    return _regular(own, night, second_chances)


def _regular(own: list[PickRow], night: date, second_chances: Iterable[SecondChance]) -> Availability:
    unlocked = {sc.pick_id for sc in second_chances if sc.bought_on <= night <= sc.expires_on}
    blocking = [
        p for p in own
        if p.id not in unlocked and abs((night - p.date).days) < COOLDOWN_DAYS
    ]
    before = [p.date for p in blocking if p.date <= night]
    if before:
        return Availability(False, max(before) + timedelta(days=COOLDOWN_DAYS), "cooldown")
    if blocking:
        return Availability(False, None, "reserved_nearby")
    return AVAILABLE


def _playoffs(own: list[PickRow], team: str, season: str, series: list[SeriesRow]) -> Availability:
    if own:
        return Availability(False, None, "playoffs_used")
    this_season = [s for s in series if s.season == season]
    first_round = [s for s in this_season if s.round == 1]
    if first_round and not any(team in (s.home_team, s.away_team) for s in first_round):
        return Availability(False, None, "not_qualified")
    for s in this_season:
        lost_home = s.home_team == team and s.home_wins < 4
        lost_away = s.away_team == team and s.away_wins < 4
        if s.status == "completed" and (lost_home or lost_away):
            return Availability(False, None, "team_eliminated")
    return AVAILABLE
```

- [ ] **Step 5: Relancer le test**

Run: `./venv/bin/python -m pytest tests/rules/test_availability.py -v`
Expected: PASS (19 cas)

- [ ] **Step 6: Commiter**

```bash
git add engine/rules/availability.py tests/rules/availability_cases.json tests/rules/test_availability.py
git commit -m "feat(rules): disponibilité des joueurs, cooldown J+30 et seconde chance (R3-R6, R15)"
```

---

### Task 6: Migration 018 : picks, seconde chance, disponibilité et trigger de validation

**Files:**
- Create: `supabase/migrations/018_picks_availability.sql`
- Create: `tests/sql/test_018_availability.py`, `tests/sql/test_018_picks_trigger.py`

**Interfaces:**
- Consumes: `tests/rules/availability_cases.json` (tâche 5), `game_type_of`/`season_of` et `games.game_type`/`season` (tâche 3).
- Produces:
  - `cooldown_days() -> int` (30) ;
  - `player_available_on(p_player_id int, p_team text, p_night date, p_season text, p_mode text, p_exclude_pick_id int default null) -> table(ok boolean, available_from date, reason text)` ;
  - table `second_chances(id, pick_id, player_id, bought_on, expires_on)` ;
  - colonnes `picks.season`, `picks.is_x2` ; `picks.mode` sans valeur par défaut ;
  - trigger `picks_validate` : `before insert or update of player_id, date, game_id`. Erreurs `P0001` au format `game_not_found`, `night_not_eligible:<type>`, `date_mismatch`, `player_not_in_game`, `player_unavailable:<reason>` (détail = `available_from`).

- [ ] **Step 1: Écrire le test de disponibilité SQL (cas partagés)**

`tests/sql/test_018_availability.py` :

```python
import json
import pathlib

import pytest

CASES = json.loads(
    (pathlib.Path(__file__).parents[1] / "rules" / "availability_cases.json").read_text()
)


def _load_fixture(pg, case):
    # Mode réplica : désactive triggers et clés étrangères, pour n'insérer
    # que les lignes utiles au cas.
    pg.execute("set local session_replication_role = replica")
    for p in case["picks"]:
        pg.execute(
            "insert into picks (id, player_id, game_id, date, mode, season) "
            "values (%s, %s, 'fixture', %s, %s, %s)",
            (p["id"], p["player_id"], p["date"], p["mode"], p["season"]),
        )
    for s in case["second_chances"]:
        pg.execute(
            "insert into second_chances (pick_id, player_id, bought_on, expires_on) "
            "values (%s, %s, %s, %s)",
            (s["pick_id"], s["player_id"], s["bought_on"], s["expires_on"]),
        )
    for s in case["series"]:
        pg.execute(
            "insert into series (season, round, home_team, away_team, home_wins, away_wins, status) "
            "values (%(season)s, %(round)s, %(home_team)s, %(away_team)s, %(home_wins)s, %(away_wins)s, %(status)s)",
            s,
        )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_disponibilite_sql_identique_au_python(pg, case):
    with pg.transaction(force_rollback=True):
        _load_fixture(pg, case)
        ok, available_from, reason = pg.execute(
            "select ok, available_from, reason from player_available_on(%s, %s, %s, %s, %s, %s)",
            (case["player_id"], case["player_team"], case["night"], case["season"],
             case["mode"], case["exclude_pick_id"]),
        ).fetchone()
    exp = case["expected"]
    assert ok is exp["ok"]
    assert (available_from.isoformat() if available_from else None) == exp["available_from"]
    assert reason == exp["reason"]


def test_cooldown_days(pg):
    assert pg.execute("select cooldown_days()").fetchone() == (30,)
```

- [ ] **Step 2: Écrire les tests du trigger et des backfills**

`tests/sql/test_018_picks_trigger.py` :

```python
import pathlib

import psycopg
import pytest

MIGRATION_018 = (
    pathlib.Path(__file__).parents[2] / "supabase" / "migrations" / "018_picks_availability.sql"
)


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values "
        "(1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G'), (3, 'LeBron', 'LAL', 'F')"
    )
    pg.execute(
        "insert into games (id, date, home_team, away_team) values "
        "('0022500100', '2025-10-25', 'DEN', 'LAL'), "
        "('0022500200', '2025-11-10', 'DEN', 'BOS'), "
        "('0022500300', '2025-11-24', 'DEN', 'PHX'), "
        "('0012600001', '2026-10-05', 'DEN', 'LAL'), "
        "('unknown_1_2025-11-12', '2025-11-12', 'DEN', 'UNK')"
    )


def test_trigger_remplit_mode_et_saison(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        assert pg.execute(
            "select mode, season from picks where date = '2025-10-25'"
        ).fetchone() == ("regular", "2025-26")


def test_trigger_refuse_cooldown(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        with pytest.raises(psycopg.errors.RaiseException, match="player_unavailable:cooldown"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500200', '2025-11-10')")


def test_trigger_accepte_j30(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-25')")
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500300', '2025-11-24')")


def test_trigger_refuse_match_ineligible(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_not_eligible:preseason"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0012600001', '2026-10-05')")
        with pytest.raises(psycopg.errors.RaiseException, match="night_not_eligible:unknown"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, 'unknown_1_2025-11-12', '2025-11-12')")


def test_trigger_refuse_joueur_absent_du_match(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="player_not_in_game"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (3, '0022500200', '2025-11-10')")


def test_trigger_refuse_date_incoherente(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="date_mismatch"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500100', '2025-10-26')")


def test_trigger_remplacement_meme_date(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022500200', '2025-11-10')")
        # R2 : on remplace le joueur de la soirée, la ligne ne se bloque pas elle-même.
        pg.execute("update picks set player_id = 2 where date = '2025-11-10'")
        pg.execute("update picks set player_id = 1 where date = '2025-11-10'")


def test_trigger_ignore_maj_score(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        # Historique incohérent inséré sans validation (comme l'import 2025-26).
        pg.execute("set local session_replication_role = replica")
        pg.execute(
            "insert into picks (player_id, game_id, date, mode, season) values "
            "(1, '0022500100', '2025-10-25', 'regular', '2025-26'), "
            "(1, '0022500200', '2025-11-10', 'regular', '2025-26')"
        )
        pg.execute("set local session_replication_role = origin")
        # Le sync met à jour le score : aucune validation ne doit se déclencher.
        pg.execute("update picks set actual_score = 44, is_x2 = true where date = '2025-11-10'")


def test_backfill_x2_et_seconde_chance(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("set local session_replication_role = replica")
        pg.execute(
            "insert into picks (player_id, game_id, date, mode, estimated_score, actual_score) values "
            "(1, '0022500100', '2025-11-02', 'regular', 106, 53), "   # x2 réel
            "(2, '0022500200', '2025-11-12', 'regular', 0, 0), "      # zéro : jamais x2
            "(3, '0022500300', '2025-11-13', 'regular', 40, 38)"      # pick normal
        )
        pg.execute("set local session_replication_role = origin")
        pg.execute(MIGRATION_018.read_text())  # rejouer la migration applique les backfills
        rows = {
            d: (x2, est)
            for d, x2, est in pg.execute(
                "select date::text, is_x2, estimated_score from picks order by date"
            ).fetchall()
        }
        assert rows["2025-11-02"] == (True, None)
        assert rows["2025-11-12"] == (False, 0)
        assert rows["2025-11-13"] == (False, 40)
        assert pg.execute(
            "select bought_on::text, expires_on::text from second_chances"
        ).fetchall() == [("2025-11-17", "2025-11-24")]
```

- [ ] **Step 3: Lancer les tests pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/sql/test_018_availability.py tests/sql/test_018_picks_trigger.py -v`
Expected: FAIL avec `UndefinedTable: relation "second_chances" does not exist` et `UndefinedFunction: player_available_on`

- [ ] **Step 4: Écrire la migration**

`supabase/migrations/018_picks_availability.sql` :

```sql
-- 018 — Picks : saison, x2 explicite, bonus Seconde chance, et règle de
-- disponibilité (R3/R4/R5/R6/R15) appliquée en base par trigger.
-- Miroir de engine/rules/availability.py : mêmes cas dans
-- tests/rules/availability_cases.json. Idempotente.

create or replace function cooldown_days() returns int
language sql immutable as $$ select 30 $$;  -- R3 : pické à J → disponible à J+30

alter table picks add column if not exists season text;
alter table picks add column if not exists is_x2 boolean not null default false;
alter table picks alter column mode drop default;  -- déduit du match par le trigger
create index if not exists idx_picks_player_season on picks(player_id, season, mode, date);

update picks p set season = season_of(p.game_id, p.date) where p.season is null;

-- Backfill x2 2025-26 : l'import stockait le score doublé dans estimated_score.
-- actual_score <> 0 : sinon les zéros (0 = 2 × 0) passeraient pour des x2.
update picks set is_x2 = true, estimated_score = null
where not is_x2 and actual_score is not null and actual_score <> 0
  and estimated_score = 2 * actual_score;

-- R15 — bonus Seconde chance, saisi à la main à l'achat.
create table if not exists second_chances (
  id serial primary key,
  pick_id integer not null references picks(id) on delete cascade,
  player_id integer not null references players(id),
  bought_on date not null,
  expires_on date not null,
  unique (pick_id)
);
alter table second_chances enable row level security;
drop policy if exists "anon read second_chances" on second_chances;
create policy "anon read second_chances" on second_chances for select using (true);

-- Seconde chance utilisées en 2025-26 (boutique : achats du 17/11 et du 13/03).
insert into second_chances (pick_id, player_id, bought_on, expires_on)
select p.id, p.player_id, b.bought_on, b.bought_on + 7
from (values (date '2025-11-12', date '2025-11-17'),
             (date '2026-03-08', date '2026-03-13')) as b(pick_date, bought_on)
join picks p on p.date = b.pick_date and p.actual_score = 0
on conflict (pick_id) do nothing;

create or replace function player_available_on(
  p_player_id int,
  p_team text,
  p_night date,
  p_season text,
  p_mode text,
  p_exclude_pick_id int default null
) returns table (ok boolean, available_from date, reason text)
language plpgsql stable as $$
declare
  v_cd int := cooldown_days();
  v_prev date;
  v_next date;
begin
  if p_mode = 'playoffs' then
    -- R4 : pick-and-drop sur toute la période PO de la saison.
    if exists (
      select 1 from picks q
      where q.player_id = p_player_id and q.season = p_season and q.mode = 'playoffs'
        and q.id is distinct from p_exclude_pick_id
    ) then
      return query select false, null::date, 'playoffs_used'::text; return;
    end if;
    -- R5 : seules les équipes du 1er tour sont qualifiées (play-in éliminé).
    if exists (select 1 from series s where s.season = p_season and s.round = 1)
       and not exists (
         select 1 from series s
         where s.season = p_season and s.round = 1
           and p_team in (s.home_team, s.away_team)
       ) then
      return query select false, null::date, 'not_qualified'::text; return;
    end if;
    -- R5 : perdant d'une série terminée.
    if exists (
      select 1 from series s
      where s.season = p_season and s.status = 'completed'
        and ((s.home_team = p_team and s.home_wins < 4)
          or (s.away_team = p_team and s.away_wins < 4))
    ) then
      return query select false, null::date, 'team_eliminated'::text; return;
    end if;
    return query select true, null::date, null::text; return;
  end if;

  -- R3 : cooldown de v_cd jours dans les deux sens, hors pick débloqué par
  -- une Seconde chance active ce soir-là (R15).
  select max(q.date) into v_prev
  from picks q
  where q.player_id = p_player_id and q.season = p_season and q.mode = 'regular'
    and q.id is distinct from p_exclude_pick_id
    and q.date <= p_night and p_night - q.date < v_cd
    and not exists (
      select 1 from second_chances sc
      where sc.pick_id = q.id and p_night between sc.bought_on and sc.expires_on
    );
  if v_prev is not null then
    return query select false, v_prev + v_cd, 'cooldown'::text; return;
  end if;

  select min(q.date) into v_next
  from picks q
  where q.player_id = p_player_id and q.season = p_season and q.mode = 'regular'
    and q.id is distinct from p_exclude_pick_id
    and q.date > p_night and q.date - p_night < v_cd
    and not exists (
      select 1 from second_chances sc
      where sc.pick_id = q.id and p_night between sc.bought_on and sc.expires_on
    );
  if v_next is not null then
    return query select false, null::date, 'reserved_nearby'::text; return;
  end if;

  return query select true, null::date, null::text;
end
$$;

-- Validation d'un pick ou d'une réservation. Ne se déclenche que si le
-- joueur, la date ou le match changent : les mises à jour de score ou de x2
-- faites par le sync ne sont jamais revalidées.
create or replace function picks_validate() returns trigger
language plpgsql as $$
declare
  g record;
  v_team text;
  a record;
begin
  select * into g from games where id = new.game_id;
  if not found then
    raise exception 'game_not_found' using errcode = 'P0001';
  end if;
  if g.game_type not in ('regular', 'cup_final', 'playoffs') then
    raise exception 'night_not_eligible:%', g.game_type using errcode = 'P0001';
  end if;
  if g.date <> new.date then
    raise exception 'date_mismatch' using errcode = 'P0001';
  end if;
  select team into v_team from players where id = new.player_id;
  if v_team is distinct from g.home_team and v_team is distinct from g.away_team then
    raise exception 'player_not_in_game' using errcode = 'P0001';
  end if;

  new.mode := case when g.game_type = 'playoffs' then 'playoffs' else 'regular' end;
  new.season := g.season;

  select * into a
  from player_available_on(new.player_id, v_team, new.date, new.season, new.mode, new.id);
  if not a.ok then
    raise exception 'player_unavailable:%', a.reason
      using errcode = 'P0001', detail = coalesce(a.available_from::text, '');
  end if;
  return new;
end
$$;
drop trigger if exists picks_validate on picks;
create trigger picks_validate before insert or update of player_id, date, game_id on picks
  for each row execute function picks_validate();
```

- [ ] **Step 5: Relancer les tests**

Run: `./venv/bin/python -m pytest tests/sql -v`
Expected: PASS (19 cas partagés + tests du trigger + `test_migrations_rejouables`)

- [ ] **Step 6: Commiter**

```bash
git add supabase/migrations/018_picks_availability.sql tests/sql/test_018_availability.py tests/sql/test_018_picks_trigger.py
git commit -m "feat(db): disponibilité en base, trigger de validation des picks, x2 et seconde chance (018)"
```

---

### Task 7: Calendrier : fermeture, match fantôme, soirées (R8, R11, R13)

**Files:**
- Create: `engine/rules/calendar.py`, `tests/rules/test_calendar.py`

**Interfaces:**
- Consumes: `game_type_of`, `is_eligible`, `mode_of` (tâche 2).
- Produces:
  - `PARIS: ZoneInfo` ;
  - `closing_at(night: date, tip_offs: Iterable[datetime | None]) -> datetime` (aware, Europe/Paris) ;
  - `is_phantom(game: dict, completed_series: list[dict]) -> bool` ;
  - dataclass `Night(date, season, mode, n_eligible_games, closing_at, is_phantom)` ;
  - `build_nights(games: list[dict], series: list[dict]) -> list[Night]`, trié par date. Les dicts `games` ont les clés de la table `games` (dont `game_type`, `season`, `tip_off` en ISO ou `datetime`) ; les dicts `series`, celles de la table `series` (dont `season`).

- [ ] **Step 1: Écrire le test**

`tests/rules/test_calendar.py` :

```python
from datetime import date, datetime, timedelta, timezone

from engine.rules.calendar import PARIS, build_nights, closing_at, is_phantom


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_closing_at_minuit_paris_par_defaut():
    # Soirée US du 04/11, premier match 19:00 ET = 01:00 Paris le 05/11 → minuit.
    c = closing_at(date(2026, 11, 4), [_utc("2026-11-05T00:00:00")])
    assert c == datetime(2026, 11, 5, 0, 0, tzinfo=PARIS)


def test_closing_at_match_avance():
    # Noël : premier match 12:00 ET = 18:00 Paris → fermeture 18:00.
    c = closing_at(date(2026, 12, 25), [_utc("2026-12-25T17:00:00"), _utc("2026-12-26T01:00:00")])
    assert c == datetime(2026, 12, 25, 18, 0, tzinfo=PARIS)


def test_closing_at_sans_horaire_connu():
    assert closing_at(date(2026, 11, 4), [None]) == datetime(2026, 11, 5, 0, 0, tzinfo=PARIS)


def test_closing_at_changement_heure_hiver():
    # Nuit du 24 au 25/10/2026 : minuit est encore en heure d'été (UTC+2).
    c = closing_at(date(2026, 10, 24), [])
    assert c.utcoffset() == timedelta(hours=2)
    # Soirée du 25/10 : minuit du 26 est en heure d'hiver (UTC+1).
    assert closing_at(date(2026, 10, 25), []).utcoffset() == timedelta(hours=1)


def test_closing_at_changement_heure_ete():
    # Soirée du 28/03/2027 : minuit du 29 est en heure d'été (UTC+2).
    assert closing_at(date(2027, 3, 28), []).utcoffset() == timedelta(hours=2)


def _game(gid, d, home, away, gtype, season="2025-26", status="scheduled", series_id=None, tip=None):
    return {"id": gid, "date": d, "home_team": home, "away_team": away, "game_type": gtype,
            "season": season, "status": status, "series_id": series_id, "tip_off": tip}


SERIES_DONE = {"id": 7, "season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL",
               "home_wins": 4, "away_wins": 1, "status": "completed"}


def test_match_fantome_par_serie():
    g = _game("0042500106", "2026-04-30", "NYK", "ATL", "playoffs", series_id=7)
    assert is_phantom(g, [SERIES_DONE])


def test_match_fantome_par_paire_sans_lien_de_serie():
    g = _game("0042500107", "2026-05-02", "ATL", "NYK", "playoffs")
    assert is_phantom(g, [SERIES_DONE])


def test_match_joue_d_une_serie_terminee_n_est_pas_fantome():
    g = _game("0042500105", "2026-04-28", "NYK", "ATL", "playoffs", status="final", series_id=7)
    assert not is_phantom(g, [SERIES_DONE])


def test_match_sr_entre_deux_equipes_d_une_serie_terminee_n_est_pas_fantome():
    # Le bug B3 de l'audit : un NYK-ATL de saison régulière disparaissait.
    g = _game("0022600050", "2026-11-02", "NYK", "ATL", "regular", season="2026-27")
    assert not is_phantom(g, [SERIES_DONE])


def test_build_nights_mode_et_comptage():
    games = [
        _game("0022600001", "2026-10-20", "BOS", "NYK", "regular", season="2026-27", tip="2026-10-20T23:30:00+00:00"),
        _game("0022600002", "2026-10-20", "LAL", "GSW", "regular", season="2026-27", tip="2026-10-21T02:00:00+00:00"),
    ]
    [n] = build_nights(games, [])
    assert (n.date, n.season, n.mode, n.n_eligible_games, n.is_phantom) == (
        date(2026, 10, 20), "2026-27", "regular", 2, False)
    assert n.closing_at == datetime(2026, 10, 21, 0, 0, tzinfo=PARIS)


def test_build_nights_ignore_soiree_sans_match_eligible():
    # Week-end All-Star, jours de play-in, présaison : pas de soirée TTFL.
    games = [
        _game("0032500001", "2026-02-15", "EST", "WST", "allstar"),
        _game("0052500101", "2026-04-14", "MIA", "CHI", "playin"),
        _game("0012600001", "2026-10-05", "DEN", "LAL", "preseason", season="2026-27"),
    ]
    assert build_nights(games, []) == []


def test_build_nights_soiree_uniquement_fantome():
    games = [_game("0042500106", "2026-04-30", "NYK", "ATL", "playoffs", series_id=7)]
    [n] = build_nights(games, [SERIES_DONE])
    assert (n.mode, n.n_eligible_games, n.is_phantom) == ("playoffs", 0, True)


def test_build_nights_finale_nba_cup_est_une_soiree_sr():
    games = [_game("0062600001", "2026-12-15", "OKC", "MIL", "cup_final", season="2026-27")]
    [n] = build_nights(games, [])
    assert (n.mode, n.n_eligible_games) == ("regular", 1)
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/rules/test_calendar.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.rules.calendar'`

- [ ] **Step 3: Implémenter**

`engine/rules/calendar.py` :

```python
"""R8 (fermeture du deck), R11 (soirées éligibles), R13 (match fantôme).

Une soirée TTFL = une date US ayant au moins un match éligible non fantôme.
Les soirées ne contenant que des matchs fantômes sont gardées avec
is_phantom=True, pour alerter si une réservation y est posée (R13).
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from engine.rules.game_types import is_eligible, mode_of

PARIS = ZoneInfo("Europe/Paris")


def closing_at(night: date, tip_offs: Iterable[datetime | None]) -> datetime:
    """R8 : 00:00 heure de Paris à la fin de la soirée, ou le premier
    tip-off s'il est plus tôt. Retourne un datetime aware en Europe/Paris."""
    midnight = datetime.combine(night + timedelta(days=1), time(0, 0), tzinfo=PARIS)
    tips = [t.astimezone(PARIS) for t in tip_offs if t is not None]
    return min([midnight, *tips])


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def is_phantom(game: dict, completed_series: list[dict]) -> bool:
    """R13 : match de PO programmé d'une série déjà terminée, la même saison.
    Lien par series_id ou, à défaut, par paire d'équipes (les matchs
    conditionnels perdent parfois leur lien de série)."""
    if game.get("game_type") != "playoffs" or game.get("status") != "scheduled":
        return False
    same_season = [s for s in completed_series if s.get("season") == game.get("season")]
    if game.get("series_id") in {s["id"] for s in same_season}:
        return True
    pairs = {_pair(s["home_team"], s["away_team"]) for s in same_season}
    return _pair(game["home_team"], game["away_team"]) in pairs


@dataclass(frozen=True)
class Night:
    date: date
    season: str
    mode: str
    n_eligible_games: int
    closing_at: datetime
    is_phantom: bool


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _as_dt(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def build_nights(games: list[dict], series: list[dict]) -> list[Night]:
    completed = [s for s in series if s.get("status") == "completed"]
    by_date: dict[date, list[dict]] = {}
    for g in games:
        if is_eligible(g.get("game_type", "unknown")):
            by_date.setdefault(_as_date(g["date"]), []).append(g)

    nights = []
    for d in sorted(by_date):
        day_games = by_date[d]
        real = [g for g in day_games if not is_phantom(g, completed)]
        reference = real or day_games
        mode = "playoffs" if any(mode_of(g["game_type"]) == "playoffs" for g in reference) else "regular"
        nights.append(Night(
            date=d,
            season=reference[0]["season"],
            mode=mode,
            n_eligible_games=len(real),
            closing_at=closing_at(d, [_as_dt(g.get("tip_off")) for g in real]),
            is_phantom=not real,
        ))
    return nights
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/rules/test_calendar.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/rules/calendar.py tests/rules/test_calendar.py
git commit -m "feat(rules): fermeture du deck, match fantôme et soirées TTFL (R8, R11, R13)"
```

---

### Task 8: Migration 019 : tables `nights` et `plan`, disponibilité par soirée

**Files:**
- Create: `supabase/migrations/019_nights_plan.sql`, `tests/sql/test_019_nights_plan.py`

**Interfaces:**
- Consumes: `player_available_on` (tâche 6), `players.active` (tâche 3).
- Produces:
  - table `nights(date pk, season, mode, n_eligible_games, closing_at, is_phantom, updated_at)`, écrite par le moteur (L1b) avec les champs de `Night` ;
  - table `plan(id, generated_at, night, player_id, is_x2, projection, p_play, value, explanation)` ;
  - fonction `player_availability(p_night date) -> table(player_id int, ok boolean, available_from date, reason text)` pour tous les joueurs actifs, vide si la soirée n'existe pas dans `nights` (une requête par page côté front).

- [ ] **Step 1: Écrire le test**

`tests/sql/test_019_nights_plan.py` :

```python
def test_player_availability_par_soiree(pg):
    with pg.transaction(force_rollback=True):
        pg.execute(
            "insert into players (id, name, team, position, active) values "
            "(1, 'Jokic', 'DEN', 'C', true), (2, 'Murray', 'DEN', 'G', true), "
            "(3, 'Retraite', 'DEN', 'F', false)"
        )
        pg.execute(
            "insert into games (id, date, home_team, away_team) values "
            "('0022600100', '2026-10-25', 'DEN', 'LAL'), ('0022600200', '2026-11-10', 'DEN', 'BOS')"
        )
        pg.execute(
            "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
            "('2026-11-10', '2026-27', 'regular', 1, '2026-11-10T23:00:00Z')"
        )
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600100', '2026-10-25')")
        rows = {
            r[0]: r[1:]
            for r in pg.execute(
                "select player_id, ok, available_from::text, reason "
                "from player_availability('2026-11-10') order by player_id"
            ).fetchall()
        }
        assert rows == {
            1: (False, "2026-11-24", "cooldown"),
            2: (True, None, None),
        }  # le joueur inactif n'apparaît pas


def test_player_availability_soiree_inconnue(pg):
    assert pg.execute("select count(*) from player_availability('2030-01-01')").fetchone() == (0,)


def test_plan_insertion(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute(
            "insert into plan (night, player_id, is_x2, projection, p_play, value, explanation) "
            "values ('2026-11-10', 1, false, 52.0, 0.95, 49.4, 'match facile à domicile')"
        )
        assert pg.execute("select count(*) from plan").fetchone() == (1,)
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/sql/test_019_nights_plan.py -v`
Expected: FAIL avec `UndefinedTable: relation "nights" does not exist`

- [ ] **Step 3: Écrire la migration**

`supabase/migrations/019_nights_plan.sql` :

```sql
-- 019 — Soirées TTFL (écrites par le moteur, lues par le front et les
-- rappels) et plan du moteur (remplacera weekly_plan en L1b). Idempotente.

create table if not exists nights (
  date date primary key,
  season text not null,
  mode text not null check (mode in ('regular', 'playoffs')),
  n_eligible_games integer not null,
  closing_at timestamptz not null,
  is_phantom boolean not null default false,
  updated_at timestamptz not null default now()
);
alter table nights enable row level security;
drop policy if exists "anon read nights" on nights;
create policy "anon read nights" on nights for select using (true);

create table if not exists plan (
  id bigserial primary key,
  generated_at timestamptz not null default now(),
  night date not null,
  player_id integer not null references players(id),
  is_x2 boolean not null default false,
  projection numeric not null,
  p_play numeric not null,
  value numeric not null,
  explanation text not null default '',
  unique (generated_at, night)
);
create index if not exists idx_plan_generated_night on plan(generated_at desc, night);
alter table plan enable row level security;
drop policy if exists "anon read plan" on plan;
create policy "anon read plan" on plan for select using (true);

-- Disponibilité de tous les joueurs actifs pour une soirée (un appel par page).
create or replace function player_availability(p_night date)
returns table (player_id int, ok boolean, available_from date, reason text)
language sql stable as $$
  select p.id, a.ok, a.available_from, a.reason
  from nights n
  cross join players p
  cross join lateral player_available_on(p.id, p.team, n.date, n.season, n.mode, null) a
  where n.date = p_night and p.active
$$;
```

- [ ] **Step 4: Relancer toute la suite**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS (suite existante + `tests/rules` + `tests/sql`)

- [ ] **Step 5: Commiter**

```bash
git add supabase/migrations/019_nights_plan.sql tests/sql/test_019_nights_plan.py
git commit -m "feat(db): tables nights et plan, disponibilité par soirée (019)"
```

---

### Task 9: Application en prod (avec le feu vert de l'utilisateur)

**Files:**
- Modify: `docs/regles-ttfl.md` (seulement si le préfixe de la finale NBA Cup diffère, voir Step 6)

**Interfaces:**
- Consumes: migrations 017-019 (tâches 3, 6, 8).
- Produces: prod à jour (002 → 019), données 2025-26 backfillées.

- [ ] **Step 1: Contrôles avant migration (lecture seule)**

```bash
set -a && . ./.env && set +a
supabase db query --linked "select count(*) filter (where estimated_score = 2*actual_score and actual_score <> 0) as x2_attendus, count(*) filter (where date in ('2025-11-12','2026-03-08') and actual_score = 0) as secondes_chances from picks"
```

Expected: `x2_attendus = 6`, `secondes_chances = 2`.

- [ ] **Step 2: Dry-run**

Run: `supabase db push --linked --dry-run`
Expected: `Would push these migrations: 017_season_game_type.sql, 018_picks_availability.sql, 019_nights_plan.sql` (les fichiers 002-013 modifiés à la tâche 1 ne sont pas rejoués : ils sont déjà dans l'historique distant).

- [ ] **Step 3: Demander le feu vert**

Présenter à l'utilisateur le résultat des étapes 1 et 2, et **attendre un « oui » explicite** avant d'écrire en prod.

- [ ] **Step 4: Appliquer**

Run: `supabase db push --linked`
Expected: `Applying migration 017…`, `018…`, `019…`, puis `Finished supabase db push.`

- [ ] **Step 5: Vérifier les backfills**

```bash
supabase db query --linked "select game_type, season, count(*) from games group by 1,2 order by 2,1"
supabase db query --linked "select count(*) filter (where is_x2) as x2, count(*) filter (where season is null) as sans_saison, count(*) filter (where mode is null) as sans_mode from picks"
supabase db query --linked "select count(*) as sans_equipe from game_logs where team is null"
supabase db query --linked "select p.date, pl.name, s.bought_on, s.expires_on from second_chances s join picks p on p.id = s.pick_id join players pl on pl.id = s.player_id"
```

Expected :
- `regular 2025-26` = 943 (871 + 72 `hist_`), `playoffs` = 101, `playin` = 6 ;
- `x2 = 6`, `sans_saison = 0`, `sans_mode = 0` ;
- `sans_equipe = 0` ;
- deux secondes chances : Mobley (12/11, 17/11 → 24/11) et Giannis (08/03, 13/03 → 20/03).

- [ ] **Step 6: Vérifier le préfixe de la finale NBA Cup**

```bash
curl -s -H "User-Agent: Mozilla/5.0" -H "Referer: https://www.nba.com/" https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['leagueSchedule']; print(d.get('seasonYear')); [print(g['gameId'], gd['gameDate'], g.get('gameLabel')) for gd in d['gameDates'] for g in gd['games'] if 'Cup' in (g.get('gameLabel') or '') and 'Championship' in (g.get('gameLabel') or '') or g['gameId'][:3] not in ('001','002','003','004','005')]"
```

Expected : la saison `2026-27` est servie, et la finale NBA Cup a un identifiant en `006…`. **Si le préfixe diffère**, mettre à jour `_PREFIX_TYPES` (`engine/rules/game_types.py`), `game_type_of` (dans une nouvelle migration `020_cup_final_prefix.sql` qui fait `create or replace function game_type_of` puis `update games set game_type = game_type_of(id)`) et `tests/rules/game_type_cases.json`, puis relancer `pytest`. Si le calendrier 2026-27 n'est pas encore publié, reporter cette vérification à la checklist de réactivation de L1b.

- [ ] **Step 7: Commiter si besoin**

Seulement si l'étape 6 a entraîné des changements :

```bash
git add engine/rules/game_types.py tests/rules/game_type_cases.json supabase/migrations/020_cup_final_prefix.sql
git commit -m "fix(rules): préfixe réel de la finale NBA Cup"
```
