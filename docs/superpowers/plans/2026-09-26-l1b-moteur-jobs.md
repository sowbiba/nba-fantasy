# L1b — Moteur et jobs : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le sync `sync/` (100 % playoffs) par le moteur `engine/`. Il projette les scores, calcule l'espérance complète (S1), propose un plan sur 30 jours sous cooldown (S2, indicatif), écrit les soirées, les recommandations et le plan, et respecte les limites des API NBA.

**Architecture:** Des couches à sens unique : `jobs → strategy → (stats, rules) → io`.
- `stats` et `strategy` sont purs et testés sans réseau ni base.
- `io` concentre Supabase (pagination, lots), cdn.nba.com, stats.nba.com et ESPN, derrière un `ApiGuard` (limiteur, retries, disjoncteur, budget).
- Deux jobs :
  - `daily_sync` (GitHub Actions, jamais stats.nba.com) ;
  - `local_nightly` (PC local : effectifs, historique complet via `LeagueGameLog`, matchups bruts).
- `sync/` est supprimé à la fin.

**Tech Stack:** Python 3.14, pytest, nba_api, httpx, supabase-py, numpy, scipy (`linear_sum_assignment`), `zoneinfo`.

**Spec:** `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md` (+ `docs/regles-ttfl.md`, `docs/strategie-ttfl.md`). Les règles viennent de `engine/rules/` (L1a, déjà en prod : migrations 017-019).

## Global Constraints

- `engine/rules/`, `engine/stats/`, `engine/strategy/`, `engine/explain/` n'importent ni Supabase, ni httpx, ni nba_api.
- Aucune lecture d'environnement à l'import : `engine.config.env()` est appelé au moment de l'exécution.
- **stats.nba.com n'est jamais appelé depuis GitHub Actions** : `NbaSource(allow_stats=False)` dans `daily_sync`, `allow_stats=True` seulement dans `local_nightly`.
- Politiques d'appel (`ApiGuard`) :
  - stats.nba.com : 5,0 s entre appels, 2 retries, disjoncteur à 3 échecs, budget 400 ;
  - cdn.nba.com : 1,0 s, 2 retries, disjoncteur à 5, budget 300 ;
  - espn : 1,0 s, 2 retries, disjoncteur à 3, budget 20.
- Toute lecture Supabase multi-lignes est paginée par 1000. Écritures par lots de 500.
- Soirée cible du jour = **date de Paris** (le deck du jour D ferme à 00:00 Paris, fin de D).
- Horizon du plan : **30 jours** (J à J+29), soit exactement une fenêtre de cooldown avec J+30. Dans cet horizon, « un joueur au plus une fois » est exactement la règle R3. Cela remplace les « 31 j » de la spec, écrits quand le cooldown était J+31.
- Valeur S1 du soir : `p_play × projection − (1 − p_play) × lock_value`. `lock_value` = meilleure espérance future décotée du joueur sur J+1…J+29. Décote `0,985^k`.
- Reco du soir (L1) = tri par valeur S1. Le plan est **indicatif** jusqu'à la validation par backtest (L2).
- Les box scores ne sont ingérés que pour les matchs éligibles (`regular`, `cup_final`, `playoffs`). Jamais pour la présaison ni le play-in.
- La synchronisation des séries de playoffs (ex-`seed_playoffs`) est hors périmètre : elle passe en L3.
- Messages de commit terminés par une ligne vide puis `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Aucune écriture en prod sans feu vert explicite de l'utilisateur (tâche 16).

## Review Focus

- **API bloquée ou qui répond vide** (Akamai, 429, CDN purgé) : le job continue avec les données en base, n'échoue pas, et le journal compte les appels. Test : tâche 13, `test_daily_sync_continue_si_nba_indisponible`.
- **Joueur absent de la table `players`** dans un box score (signature récente, two-way) : sa ligne est ignorée au lieu de faire échouer tout le lot (clé étrangère). Test : tâche 13, `test_daily_sync_ignore_logs_de_joueurs_inconnus`.
- **Début de saison sans aucun match joué** : projection issue de la saison précédente (prior), jamais 0 pour tout le monde (bug B5 de l'audit). Test : tâche 12, `test_decide_debut_de_saison_utilise_le_prior`.
- **Soirée où l'utilisateur a déjà un pick ou une réservation** : soirée fixée, jamais réaffectée par le plan, et le joueur réservé est exclu des autres soirées à moins de 30 jours. Test : tâche 12, `test_decide_respecte_les_reservations`.
- **Joueur en cooldown ou « Out » ce soir** : jamais recommandé ce soir. Test : tâche 12, `test_decide_exclut_cooldown_et_out`.

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `supabase/migrations/020_engine_outputs.sql` | Colonnes S1 sur `recommendations`, `sync_log.job` / `api_calls` |
| `engine/config.py` | `env(name)` lu à l'appel |
| `engine/rules/game_types.py` | + `season_for_date`, `previous_season` |
| `engine/io/guard.py` | `ApiGuard` : limiteur, retries, disjoncteur, budget |
| `engine/io/repo.py` | `SupabaseRepo` : lectures paginées, écritures par lots |
| `engine/io/nba.py` | Parseurs purs + `NbaSource` (cdn / stats) |
| `engine/io/espn.py` | Blessures ESPN (déplacé depuis `sync/injuries.py`) |
| `engine/stats/availability_prob.py` | P(joue) : statut, DNP récents, back-to-back |
| `engine/stats/profile.py` | Profil joueur : efficacité, minutes de rôle, prior d'intersaison (S6) |
| `engine/stats/team_defense.py` | Facteurs défensifs par poste, saison + prior régressé |
| `engine/stats/projection.py` | Projection d'un match, repos |
| `engine/stats/aggregates.py` | Colonnes `players.avg_*` pour le front actuel |
| `engine/strategy/value.py` | Valeur S1, décote, `lock_value` |
| `engine/strategy/planner.py` | Affectation joueurs × soirées (`linear_sum_assignment`) |
| `engine/strategy/regular.py` | `decide()` : cellules, recos du soir, plan |
| `engine/explain/texts.py` | Argumentaires FR des recos et du plan |
| `engine/jobs/daily_sync.py` | Job GitHub Actions |
| `engine/jobs/local_nightly.py` | Job cron local (stats.nba.com) |
| `tests/io/`, `tests/stats/`, `tests/strategy/`, `tests/jobs/` | Tests unitaires et d'intégration (faux repo / fausses sources) |
| `.github/workflows/daily-sync.yml`, `ci.yml`, `requirements*.txt`, `README.md`, `docs/operations.md`, `docs/strategie-ttfl.md` | Bascule et documentation |
| `sync/`, `tests/test_*.py` hérités | Supprimés (tâche 15) |
| `docs/reactivation-saison.md` | Checklist de réactivation (tâche 16) |

Commande de test utilisée partout (depuis la racine du dépôt ; Postgres de test sur `localhost:55432`) :

```bash
TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest -q
```

Tant que `sync/` existe (jusqu'à la tâche 15), les anciens tests importent `sync.config`, qui lit l'environnement. Préfixer alors aussi par `SUPABASE_URL=http://localhost SUPABASE_KEY=test SUPABASE_SERVICE_KEY=test`.

---

### Task 1: Migration 020 : sorties du moteur

**Files:**
- Create: `supabase/migrations/020_engine_outputs.sql`, `tests/sql/test_020_engine_outputs.py`

**Interfaces:**
- Produces:
  - colonnes `recommendations.projection`, `p_play`, `value`, `lock_value` (numeric), `locked_until` (date), `best_future` (text) ;
  - `sync_log.job` (text, défaut `'daily_sync'`), `sync_log.api_calls` (jsonb, défaut `{}`).

- [ ] **Step 1: Écrire le test**

`tests/sql/test_020_engine_outputs.py` :

```python
def test_recommendations_colonnes_s1(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute(
            "insert into recommendations (date, player_id, rank, estimated_score, tier, "
            "projection, p_play, value, lock_value, locked_until, best_future) values "
            "('2026-11-10', 1, 1, 49.4, 'elite', 52.0, 0.95, 47.1, 38.0, '2026-12-10', 'jeudi 20 vs WAS')"
        )
        assert pg.execute("select value, locked_until::text from recommendations").fetchone() == (47.1, "2026-12-10")


def test_sync_log_job_et_api_calls(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into sync_log (status) values ('running')")
        assert pg.execute("select job, api_calls from sync_log").fetchone() == ("daily_sync", {})
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql/test_020_engine_outputs.py -v`
Expected: FAIL avec `UndefinedColumn: column "projection" of relation "recommendations" does not exist`

- [ ] **Step 3: Écrire la migration**

`supabase/migrations/020_engine_outputs.sql` :

```sql
-- 020 — Sorties du moteur L1b : espérance complète (S1) sur les
-- recommandations du soir, et journal des jobs (daily_sync / local_nightly)
-- avec le décompte des appels API par hôte. Idempotente.

alter table recommendations add column if not exists projection numeric;
alter table recommendations add column if not exists p_play numeric;
alter table recommendations add column if not exists value numeric;
alter table recommendations add column if not exists lock_value numeric;
alter table recommendations add column if not exists locked_until date;
alter table recommendations add column if not exists best_future text;

alter table sync_log add column if not exists job text not null default 'daily_sync';
alter table sync_log add column if not exists api_calls jsonb not null default '{}'::jsonb;
create index if not exists idx_sync_log_job_started on sync_log(job, started_at desc);
```

- [ ] **Step 4: Relancer les tests SQL**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -v`
Expected: PASS (dont `test_migrations_rejouables`)

- [ ] **Step 5: Commiter**

```bash
git add supabase/migrations/020_engine_outputs.sql tests/sql/test_020_engine_outputs.py
git commit -m "feat(db): colonnes S1 des recommandations et journal des jobs (020)"
```

---

### Task 2: Configuration et saisons

**Files:**
- Create: `engine/config.py`, `tests/rules/test_seasons.py`
- Modify: `engine/rules/game_types.py`

**Interfaces:**
- Produces:
  - `engine.config.env(name: str) -> str` (charge `.env` puis lit ; `RuntimeError` si absent) ;
  - `season_for_date(d: date) -> str` ;
  - `previous_season(season: str) -> str`.

- [ ] **Step 1: Écrire le test**

`tests/rules/test_seasons.py` :

```python
from datetime import date

import pytest

from engine.config import env
from engine.rules.game_types import previous_season, season_for_date


@pytest.mark.parametrize("d,expected", [
    (date(2026, 10, 20), "2026-27"),
    (date(2026, 9, 1), "2026-27"),
    (date(2027, 4, 15), "2026-27"),
    (date(2026, 8, 31), "2025-26"),
])
def test_season_for_date(d, expected):
    assert season_for_date(d) == expected


def test_previous_season():
    assert previous_season("2026-27") == "2025-26"
    assert previous_season("2000-01") == "1999-00"


def test_env_absent(monkeypatch):
    monkeypatch.delenv("TTFL_VARIABLE_INEXISTANTE", raising=False)
    with pytest.raises(RuntimeError, match="TTFL_VARIABLE_INEXISTANTE"):
        env("TTFL_VARIABLE_INEXISTANTE")


def test_env_present(monkeypatch):
    monkeypatch.setenv("TTFL_TEST_VAR", "ok")
    assert env("TTFL_TEST_VAR") == "ok"
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/rules/test_seasons.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.config'`

- [ ] **Step 3: Implémenter**

`engine/config.py` :

```python
"""Accès à l'environnement, lu au moment de l'appel (jamais à l'import)."""
import os

from dotenv import load_dotenv


def env(name: str) -> str:
    load_dotenv()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"variable d'environnement manquante : {name}")
    return value
```

Dans `engine/rules/game_types.py`, ajouter après `_season_label`, puis réécrire le repli de `season_of` :

```python
def season_for_date(d: date) -> str:
    """Saison NBA d'une date : à partir de septembre, la saison qui commence."""
    return _season_label(d.year if d.month >= 9 else d.year - 1)


def previous_season(season: str) -> str:
    return _season_label(int(season[:4]) - 1)


def season_of(game_id: str, game_date: date) -> str:
    if game_id[:3] in _PREFIX_TYPES and game_id[3:5].isdigit():
        return _season_label(2000 + int(game_id[3:5]))
    return season_for_date(game_date)
```

- [ ] **Step 4: Lancer la suite**

Run: `./venv/bin/python -m pytest tests/rules -v`
Expected: PASS (dont les 19 cas de `test_game_types.py`, inchangés)

- [ ] **Step 5: Commiter**

```bash
git add engine/config.py engine/rules/game_types.py tests/rules/test_seasons.py
git commit -m "feat(engine): configuration à l'appel et helpers de saison"
```

---

### Task 3: `ApiGuard` : limiteur, retries, disjoncteur, budget

**Files:**
- Create: `engine/io/__init__.py`, `engine/io/guard.py`, `tests/io/__init__.py`, `tests/io/test_guard.py`

**Interfaces:**
- Produces:
  - `HostPolicy(min_interval, max_retries, breaker_threshold, budget, base_backoff=2.0)` ;
  - `DEFAULT_POLICIES: dict[str, HostPolicy]` (clés `"stats.nba.com"`, `"cdn.nba.com"`, `"espn"`) ;
  - exceptions `BreakerOpen`, `BudgetExceeded` ;
  - `ApiGuard(policies=None, *, sleep=time.sleep, clock=time.monotonic)` avec :
    - `call(host, fn, *, is_empty=lambda r: False)` ;
    - `is_open(host) -> bool` ;
    - `summary() -> dict[str, dict[str, int]]` (`{"calls", "failures"}` par hôte).

- [ ] **Step 1: Écrire le test**

`tests/io/__init__.py` : vide.

`tests/io/test_guard.py` :

```python
import pytest

from engine.io.guard import ApiGuard, BreakerOpen, BudgetExceeded, HostPolicy


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _guard(**policy):
    fc = FakeClock()
    p = HostPolicy(**{"min_interval": 5.0, "max_retries": 2, "breaker_threshold": 3, "budget": 10, **policy})
    return ApiGuard({"h": p}, sleep=fc.sleep, clock=fc.clock), fc


def test_intervalle_minimal_entre_appels():
    g, fc = _guard()
    g.call("h", lambda: 1)
    g.call("h", lambda: 2)
    assert fc.sleeps == [5.0]


def test_retry_sur_exception_puis_succes():
    g, fc = _guard(min_interval=0.0)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ConnectionError("boom")
        return "ok"

    assert g.call("h", flaky) == "ok"
    assert fc.sleeps == [2.0]           # backoff base 2 s × 2^0
    assert g.summary() == {"h": {"calls": 2, "failures": 0}}


def test_retry_after_respecte():
    g, fc = _guard(min_interval=0.0)

    class Resp:
        headers = {"Retry-After": "7"}

    class TooMany(Exception):
        response = Resp()

    calls = []

    def limited():
        calls.append(1)
        if len(calls) == 1:
            raise TooMany()
        return "ok"

    assert g.call("h", limited) == "ok"
    assert fc.sleeps == [7.0]


def test_echec_definitif_releve_l_exception_et_compte():
    g, _ = _guard(min_interval=0.0)
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert g.summary()["h"] == {"calls": 3, "failures": 1}


def test_reponse_vide_retentee_puis_rendue():
    g, _ = _guard(min_interval=0.0)
    assert g.call("h", lambda: [], is_empty=lambda r: not r) == []
    assert g.summary()["h"] == {"calls": 3, "failures": 1}


def test_disjoncteur_s_ouvre_et_bloque_sans_appel():
    g, _ = _guard(min_interval=0.0, max_retries=0, breaker_threshold=2)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert g.is_open("h")
    called = []
    with pytest.raises(BreakerOpen):
        g.call("h", lambda: called.append(1))
    assert called == []


def test_succes_remet_le_compteur_du_disjoncteur_a_zero():
    g, _ = _guard(min_interval=0.0, max_retries=0, breaker_threshold=2)
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    g.call("h", lambda: "ok")
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert not g.is_open("h")


def test_budget_depasse():
    g, _ = _guard(min_interval=0.0, budget=2)
    g.call("h", lambda: 1)
    g.call("h", lambda: 2)
    with pytest.raises(BudgetExceeded):
        g.call("h", lambda: 3)
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/io/test_guard.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.io'`

- [ ] **Step 3: Implémenter**

`engine/io/__init__.py` : vide.

`engine/io/guard.py` :

```python
"""Garde-fou des appels API externes (spec §5).

Par hôte : intervalle minimal entre appels, retries avec attente croissante
(ou Retry-After), disjoncteur après N échecs consécutifs, budget d'appels
par job. Akamai (stats.nba.com) répond parfois 200 avec un contenu vide :
`is_empty` permet de traiter ce cas comme un échec à retenter.
"""
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


class BreakerOpen(RuntimeError):
    """Hôte coupé pour ce passage après trop d'échecs consécutifs."""


class BudgetExceeded(RuntimeError):
    """Budget d'appels de l'hôte épuisé pour ce job."""


@dataclass(frozen=True)
class HostPolicy:
    min_interval: float
    max_retries: int
    breaker_threshold: int
    budget: int
    base_backoff: float = 2.0


DEFAULT_POLICIES = {
    "stats.nba.com": HostPolicy(min_interval=5.0, max_retries=2, breaker_threshold=3, budget=400),
    "cdn.nba.com": HostPolicy(min_interval=1.0, max_retries=2, breaker_threshold=5, budget=300),
    "espn": HostPolicy(min_interval=1.0, max_retries=2, breaker_threshold=3, budget=20),
}


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    try:
        value = headers.get("Retry-After")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class ApiGuard:
    def __init__(self, policies: dict[str, HostPolicy] | None = None, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.policies = policies or DEFAULT_POLICIES
        self._sleep = sleep
        self._clock = clock
        self._last_call: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._calls: dict[str, int] = {}
        self._failures: dict[str, int] = {}

    def is_open(self, host: str) -> bool:
        return self._consecutive_failures.get(host, 0) >= self.policies[host].breaker_threshold

    def summary(self) -> dict[str, dict[str, int]]:
        hosts = set(self._calls) | set(self._failures)
        return {h: {"calls": self._calls.get(h, 0), "failures": self._failures.get(h, 0)} for h in sorted(hosts)}

    def _wait_turn(self, host: str, policy: HostPolicy) -> None:
        last = self._last_call.get(host)
        if last is not None:
            elapsed = self._clock() - last
            if elapsed < policy.min_interval:
                self._sleep(policy.min_interval - elapsed)
        self._last_call[host] = self._clock()

    def call(self, host: str, fn: Callable[[], T], *,
             is_empty: Callable[[T], bool] = lambda r: False) -> T:
        policy = self.policies[host]
        if self.is_open(host):
            raise BreakerOpen(host)
        last_exc: Exception | None = None
        result = None
        for attempt in range(policy.max_retries + 1):
            if self._calls.get(host, 0) >= policy.budget:
                raise BudgetExceeded(host)
            self._wait_turn(host, policy)
            self._calls[host] = self._calls.get(host, 0) + 1
            delay = None
            try:
                result = fn()
            except Exception as exc:  # réseau, 429, 5xx, timeout
                last_exc = exc
                delay = _retry_after(exc)
            else:
                last_exc = None
                if not is_empty(result):
                    self._consecutive_failures[host] = 0
                    return result
            if attempt < policy.max_retries:
                self._sleep(delay if delay is not None else policy.base_backoff * (2 ** attempt))
        self._consecutive_failures[host] = self._consecutive_failures.get(host, 0) + 1
        self._failures[host] = self._failures.get(host, 0) + 1
        if last_exc is not None:
            raise last_exc
        return result
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/io/test_guard.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/io tests/io
git commit -m "feat(io): ApiGuard (limiteur, retries, disjoncteur, budget)"
```

---

### Task 4: `SupabaseRepo` : lectures paginées et écritures par lots

**Files:**
- Create: `engine/io/repo.py`, `tests/io/fake_supabase.py`, `tests/io/test_repo.py`

**Interfaces:**
- Consumes: `engine.config.env`.
- Produces: `SupabaseRepo(client)`, `SupabaseRepo.from_env()`, et les méthodes (dates en `date`, retours en listes de `dict` tels que PostgREST les renvoie) :
  - lectures : `load_players()`, `load_games_between(start, end)`, `load_games_of_seasons(seasons)`, `load_game_logs(seasons)`, `load_series(season)`, `load_picks(season)`, `load_second_chances()`, `game_ids_with_logs(game_ids) -> set[str]`, `game_ids_with_matchups(game_ids) -> set[str]` ;
  - écritures : `upsert_games(rows)`, `upsert_players(rows)`, `upsert_game_logs(rows)`, `upsert_matchups_raw(rows)`, `set_inactive(player_ids)`, `set_pick_score(pick_id, score)`, `replace_nights(start, rows)`, `replace_recommendations(night, rows)`, `write_plan(rows, keep_since)` ;
  - journal : `start_log(job) -> int`, `finish_log(log_id, *, status, players_updated=0, error=None, api_calls=None)`.
- Produces (tests) : `tests/io/fake_supabase.FakeClient(tables: dict[str, list[dict]])`, qui enregistre les opérations dans `.ops`.

- [ ] **Step 1: Écrire le faux client et le test**

`tests/io/fake_supabase.py` :

```python
"""Faux client supabase-py : chaînage minimal, pagination par range(),
journal des écritures dans `ops`. Suffisant pour tester SupabaseRepo."""


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self._range = None
        self._write = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, *a):
        return self

    def in_(self, *a):
        return self

    def gte(self, *a):
        return self

    def lte(self, *a):
        return self

    def lt(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def upsert(self, rows, on_conflict=None):
        self._write = ("upsert", self.table, len(rows), on_conflict)
        return self

    def insert(self, rows):
        n = len(rows) if isinstance(rows, list) else 1
        self._write = ("insert", self.table, n, None)
        return self

    def update(self, payload):
        self._write = ("update", self.table, payload, None)
        return self

    def delete(self):
        self._write = ("delete", self.table, None, None)
        return self

    def execute(self):
        if self._write:
            self.client.ops.append(self._write)
            if self._write[0] == "insert":
                return _Resp([{"id": 42}])
            return _Resp([])
        rows = self.client.tables.get(self.table, [])
        if self._range:
            start, end = self._range
            return _Resp(rows[start:end + 1])
        return _Resp(rows)


class FakeClient:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.ops = []

    def table(self, name):
        return _Query(self, name)
```

`tests/io/test_repo.py` :

```python
from datetime import date

from engine.io.repo import SupabaseRepo
from tests.io.fake_supabase import FakeClient


def test_lecture_paginee_recupere_toutes_les_lignes():
    players = [{"id": i} for i in range(2500)]
    repo = SupabaseRepo(FakeClient({"players": players}))
    assert len(repo.load_players()) == 2500


def test_upsert_par_lots_de_500():
    client = FakeClient()
    SupabaseRepo(client).upsert_game_logs([{"player_id": i, "game_id": "g"} for i in range(1200)])
    assert client.ops == [
        ("upsert", "game_logs", 500, "player_id,game_id"),
        ("upsert", "game_logs", 500, "player_id,game_id"),
        ("upsert", "game_logs", 200, "player_id,game_id"),
    ]


def test_replace_recommendations_supprime_puis_insere():
    client = FakeClient()
    SupabaseRepo(client).replace_recommendations(date(2026, 11, 10), [{"player_id": 1}])
    assert [op[0] for op in client.ops] == ["delete", "insert"]


def test_replace_recommendations_vide_supprime_seulement():
    client = FakeClient()
    SupabaseRepo(client).replace_recommendations(date(2026, 11, 10), [])
    assert [op[0] for op in client.ops] == ["delete"]


def test_game_ids_with_logs_sans_ids_ne_requete_pas():
    client = FakeClient()
    assert SupabaseRepo(client).game_ids_with_logs(set()) == set()


def test_start_log_renvoie_l_id():
    assert SupabaseRepo(FakeClient()).start_log("daily_sync") == 42
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/io/test_repo.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.io.repo'`

- [ ] **Step 3: Implémenter**

`engine/io/repo.py` :

```python
"""Accès Supabase du moteur.

Toute lecture multi-lignes est paginée (PostgREST plafonne à 1000 lignes
par requête : audit §2) et toute écriture de masse part par lots de 500.
"""
from datetime import UTC, date, datetime
from typing import Callable, Iterable

PAGE = 1000
CHUNK = 500


class SupabaseRepo:
    def __init__(self, client):
        self.c = client

    @classmethod
    def from_env(cls) -> "SupabaseRepo":
        from supabase import create_client

        from engine.config import env
        return cls(create_client(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY")))

    # --- mécanique -------------------------------------------------------
    def _all(self, make_query: Callable) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            chunk = make_query().range(offset, offset + PAGE - 1).execute().data or []
            rows.extend(chunk)
            if len(chunk) < PAGE:
                return rows
            offset += PAGE

    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        for i in range(0, len(rows), CHUNK):
            self.c.table(table).upsert(rows[i:i + CHUNK], on_conflict=on_conflict).execute()

    def _ids_present(self, table: str, game_ids: Iterable[str]) -> set[str]:
        ids = sorted(set(game_ids))
        if not ids:
            return set()
        found: set[str] = set()
        for i in range(0, len(ids), 100):
            part = ids[i:i + 100]
            rows = self._all(lambda: self.c.table(table).select("game_id").in_("game_id", part).order("game_id"))
            found |= {r["game_id"] for r in rows}
        return found

    # --- lectures --------------------------------------------------------
    def load_players(self) -> list[dict]:
        return self._all(lambda: self.c.table("players").select("*").order("id"))

    def load_games_between(self, start: date, end: date) -> list[dict]:
        return self._all(lambda: self.c.table("games").select("*")
                         .gte("date", start.isoformat()).lte("date", end.isoformat()).order("id"))

    def load_games_of_seasons(self, seasons: list[str]) -> list[dict]:
        return self._all(lambda: self.c.table("games")
                         .select("id,date,home_team,away_team,game_type,season,status")
                         .in_("season", seasons).order("id"))

    def load_game_logs(self, seasons: list[str]) -> list[dict]:
        return self._all(lambda: self.c.table("game_logs")
                         .select("player_id,game_id,date,season,team,minutes,ttfl_score,is_home")
                         .in_("season", seasons).order("id"))

    def load_series(self, season: str) -> list[dict]:
        return self._all(lambda: self.c.table("series").select("*").eq("season", season).order("id"))

    def load_picks(self, season: str) -> list[dict]:
        return self._all(lambda: self.c.table("picks")
                         .select("id,player_id,game_id,date,mode,season,actual_score,is_x2")
                         .eq("season", season).order("id"))

    def load_second_chances(self) -> list[dict]:
        return self._all(lambda: self.c.table("second_chances")
                         .select("pick_id,player_id,bought_on,expires_on").order("id"))

    def game_ids_with_logs(self, game_ids: Iterable[str]) -> set[str]:
        return self._ids_present("game_logs", game_ids)

    def game_ids_with_matchups(self, game_ids: Iterable[str]) -> set[str]:
        return self._ids_present("box_score_matchups_raw", game_ids)

    # --- écritures -------------------------------------------------------
    def upsert_games(self, rows: list[dict]) -> None:
        self._upsert("games", rows, "id")

    def upsert_players(self, rows: list[dict]) -> None:
        self._upsert("players", rows, "id")

    def upsert_game_logs(self, rows: list[dict]) -> None:
        self._upsert("game_logs", rows, "player_id,game_id")

    def upsert_matchups_raw(self, rows: list[dict]) -> None:
        self._upsert("box_score_matchups_raw", rows, "game_id,off_player_id,def_player_id")

    def set_inactive(self, player_ids: Iterable[int]) -> None:
        ids = sorted(set(player_ids))
        for i in range(0, len(ids), 100):
            self.c.table("players").update({"active": False}).in_("id", ids[i:i + 100]).execute()

    def set_pick_score(self, pick_id: int, score: int) -> None:
        self.c.table("picks").update({"actual_score": score}).eq("id", pick_id).execute()

    def replace_nights(self, start: date, rows: list[dict]) -> None:
        self.c.table("nights").delete().gte("date", start.isoformat()).execute()
        if rows:
            self.c.table("nights").insert(rows).execute()

    def replace_recommendations(self, night: date, rows: list[dict]) -> None:
        self.c.table("recommendations").delete().eq("date", night.isoformat()).execute()
        if rows:
            self.c.table("recommendations").insert(rows).execute()

    def write_plan(self, rows: list[dict], keep_since: datetime) -> None:
        if rows:
            self.c.table("plan").insert(rows).execute()
        self.c.table("plan").delete().lt("generated_at", keep_since.isoformat()).execute()

    # --- journal ---------------------------------------------------------
    def start_log(self, job: str) -> int:
        res = self.c.table("sync_log").insert({
            "job": job, "status": "running", "started_at": datetime.now(UTC).isoformat(),
        }).execute()
        return res.data[0]["id"]

    def finish_log(self, log_id: int, *, status: str, players_updated: int = 0,
                   error: str | None = None, api_calls: dict | None = None) -> None:
        self.c.table("sync_log").update({
            "status": status,
            "finished_at": datetime.now(UTC).isoformat(),
            "players_updated": players_updated,
            "error_message": (error or "")[:500] or None,
            "api_calls": api_calls or {},
        }).eq("id", log_id).execute()
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/io/test_repo.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/io/repo.py tests/io/fake_supabase.py tests/io/test_repo.py
git commit -m "feat(io): SupabaseRepo paginé, écritures par lots"
```

---

### Task 5: Source NBA : parseurs purs et `NbaSource`

**Files:**
- Create: `engine/io/nba.py`, `tests/io/test_nba_parsers.py`

**Interfaces:**
- Consumes: `ApiGuard`, `BreakerOpen`, `BudgetExceeded` (tâche 3) ; `engine.rules.scoring.compute_ttfl_score`.
- Produces:
  - `parse_schedule(payload, start, end) -> list[dict]` : clés `id, date, home_team, away_team, tip_off`, **sans `status`**, pour ne jamais écraser un statut live ou final ;
  - `parse_scoreboard(scoreboard, today) -> list[dict]` : clés `id, date, home_team, away_team, tip_off, status, home_score, away_score` ;
  - `parse_live_box_score(game, game_date) -> list[dict]` : lignes `game_logs` avec les clés `player_id, game_id, date, team, pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov, fouls, minutes, ttfl_score, is_home` ;
  - `parse_league_game_log(rows) -> tuple[dict[str, dict], list[dict], dict[int, dict]]` : (matchs par id, lignes `game_logs`, `{player_id: {"id", "name", "team"}}`) ;
  - `parse_roster(rows, tricode) -> list[dict]` : `{id, name, team, position, active: True}` ;
  - `parse_matchups(records, game_id) -> list[dict]` (mêmes clés que l'ancien `fetch_box_score_matchups`) ;
  - `NbaSource(guard, *, allow_stats=False)` : `schedule(start, end)`, `scoreboard(today)`, `box_score(game_id, game_date)`, `league_game_log(season, season_type, date_from=None)`, `roster(team_id, tricode)`, `matchups(game_id)`. Les trois derniers lèvent `RuntimeError` si `allow_stats=False`.

- [ ] **Step 1: Écrire le test**

`tests/io/test_nba_parsers.py` :

```python
from datetime import date

import pytest

from engine.io.guard import ApiGuard
from engine.io.nba import (
    NbaSource, parse_league_game_log, parse_live_box_score, parse_matchups,
    parse_roster, parse_schedule, parse_scoreboard,
)

SCHEDULE = {"leagueSchedule": {"gameDates": [
    {"gameDate": "10/20/2026 00:00:00", "games": [
        {"gameId": "0022600001", "gameDateTimeUTC": "2026-10-20T23:30:00Z",
         "homeTeam": {"teamTricode": "BOS"}, "awayTeam": {"teamTricode": "NYK"}},
    ]},
    {"gameDate": "12/31/2026 00:00:00", "games": [
        {"gameId": "0022600500", "homeTeam": {"teamTricode": "LAL"}, "awayTeam": {}},
    ]},
]}}


def test_parse_schedule_fenetre_et_sans_statut():
    rows = parse_schedule(SCHEDULE, date(2026, 10, 1), date(2026, 11, 30))
    assert rows == [{"id": "0022600001", "date": "2026-10-20", "home_team": "BOS",
                     "away_team": "NYK", "tip_off": "2026-10-20T23:30:00Z"}]


def test_parse_schedule_equipe_inconnue_devient_tbd():
    rows = parse_schedule(SCHEDULE, date(2026, 12, 1), date(2027, 1, 31))
    assert rows[0]["away_team"] == "TBD"


def test_parse_scoreboard_statuts_et_date_du_scoreboard():
    sb = {"gameDate": "2026-10-20", "games": [
        {"gameId": "0022600001", "gameStatus": 3, "gameTimeUTC": "2026-10-20T23:30:00Z",
         "homeTeam": {"teamTricode": "BOS", "score": 110}, "awayTeam": {"teamTricode": "NYK", "score": 104}},
        {"gameId": "0022600002", "gameStatus": 1, "gameTimeUTC": None,
         "homeTeam": {"teamTricode": "LAL", "score": 0}, "awayTeam": {"teamTricode": "GSW", "score": 0}},
    ]}
    rows = parse_scoreboard(sb, date(2026, 10, 21))
    assert rows[0] == {"id": "0022600001", "date": "2026-10-20", "home_team": "BOS", "away_team": "NYK",
                       "tip_off": "2026-10-20T23:30:00Z", "status": "final",
                       "home_score": 110, "away_score": 104}
    assert rows[1]["status"] == "scheduled" and rows[1]["home_score"] is None


def _player(pid, minutes, **stats):
    base = {"points": 0, "reboundsTotal": 0, "assists": 0, "steals": 0, "blocks": 0,
            "fieldGoalsMade": 0, "fieldGoalsAttempted": 0, "threePointersMade": 0,
            "threePointersAttempted": 0, "freeThrowsMade": 0, "freeThrowsAttempted": 0,
            "turnovers": 0, "foulsPersonal": 0, "minutes": minutes}
    base.update(stats)
    return {"personId": pid, "firstName": "A", "familyName": "B", "statistics": base}


def test_parse_live_box_score_date_us_equipe_et_dnp():
    game = {"gameId": "0022600001",
            "homeTeam": {"teamTricode": "BOS", "players": [
                _player(1, "PT34M12.00S", points=28, reboundsTotal=10, assists=6, steals=2, blocks=1,
                        fieldGoalsMade=11, fieldGoalsAttempted=20, threePointersMade=3,
                        threePointersAttempted=7, freeThrowsMade=3, freeThrowsAttempted=4, turnovers=4)]},
            "awayTeam": {"teamTricode": "NYK", "players": [_player(2, "PT00M00.00S")]}}
    rows = parse_live_box_score(game, "2026-10-20")
    star = next(r for r in rows if r["player_id"] == 1)
    assert (star["date"], star["team"], star["minutes"], star["ttfl_score"], star["is_home"]) == (
        "2026-10-20", "BOS", 34, 46, True)
    dnp = next(r for r in rows if r["player_id"] == 2)
    assert (dnp["minutes"], dnp["ttfl_score"], dnp["is_home"], dnp["team"]) == (0, 0, False, "NYK")


LGL = [
    {"PLAYER_ID": 1, "PLAYER_NAME": "Jokic", "TEAM_ABBREVIATION": "DEN", "GAME_ID": "0022500010",
     "GAME_DATE": "2025-10-22", "MATCHUP": "DEN vs. GSW", "MIN": 35, "PTS": 30, "REB": 12, "AST": 10,
     "STL": 1, "BLK": 1, "FGM": 12, "FGA": 20, "FG3M": 2, "FG3A": 5, "FTM": 4, "FTA": 5, "TOV": 3, "PF": 2},
    {"PLAYER_ID": 2, "PLAYER_NAME": "Curry", "TEAM_ABBREVIATION": "GSW", "GAME_ID": "0022500010",
     "GAME_DATE": "2025-10-22", "MATCHUP": "GSW @ DEN", "MIN": "31:30", "PTS": 25, "REB": 4, "AST": 6,
     "STL": 1, "BLK": 0, "FGM": 9, "FGA": 19, "FG3M": 5, "FG3A": 12, "FTM": 2, "FTA": 2, "TOV": 2, "PF": 1},
]


def test_parse_league_game_log():
    games, logs, players = parse_league_game_log(LGL)
    assert games == {"0022500010": {"id": "0022500010", "date": "2025-10-22", "home_team": "DEN",
                                    "away_team": "GSW", "status": "final"}}
    jokic = next(l for l in logs if l["player_id"] == 1)
    assert (jokic["team"], jokic["is_home"], jokic["minutes"], jokic["fouls"]) == ("DEN", True, 35, 2)
    assert jokic["ttfl_score"] == 30 + 12 + 10 + 1 + 1 + 12 + 2 + 4 - 3 - 8 - 3 - 1
    curry = next(l for l in logs if l["player_id"] == 2)
    assert (curry["is_home"], curry["minutes"]) == (False, 31)
    assert players[2] == {"id": 2, "name": "Curry", "team": "GSW"}


def test_parse_league_game_log_format_date_texte():
    rows = [dict(LGL[0], GAME_DATE="OCT 22, 2025")]
    games, logs, _ = parse_league_game_log(rows)
    assert logs[0]["date"] == "2025-10-22"


def test_parse_roster_postes():
    rows = [{"PLAYER_ID": 1, "PLAYER": "A", "POSITION": "G-F"},
            {"PLAYER_ID": 2, "PLAYER": "B", "POSITION": "Center"},
            {"PLAYER_ID": 3, "PLAYER": "C", "POSITION": ""}]
    assert [(r["id"], r["position"], r["team"], r["active"]) for r in parse_roster(rows, "DEN")] == [
        (1, "G", "DEN", True), (2, "C", "DEN", True), (3, "F", "DEN", True)]


def test_parse_matchups():
    rec = {"gameId": "0022600001", "teamTricode": "BOS", "personIdOff": 1, "firstNameOff": "A",
           "familyNameOff": "B", "personIdDef": 2, "firstNameDef": "C", "familyNameDef": "D",
           "matchupMinutesSort": 300.0, "partialPossessions": 20.5, "playerPoints": 8,
           "matchupAssists": 1, "matchupTurnovers": 0, "matchupBlocks": 0,
           "matchupFieldGoalsMade": 3, "matchupFieldGoalsAttempted": 6,
           "matchupThreePointersMade": 1, "matchupThreePointersAttempted": 2,
           "matchupFreeThrowsMade": 1, "matchupFreeThrowsAttempted": 1}
    [row] = parse_matchups([rec], "0022600001")
    assert (row["off_player_id"], row["def_player_id"], row["matchup_seconds"], row["player_points"]) == (1, 2, 300.0, 8)


def test_stats_nba_interdit_depuis_github():
    src = NbaSource(ApiGuard(), allow_stats=False)
    with pytest.raises(RuntimeError, match="stats.nba.com"):
        src.league_game_log("2026-27", "Regular Season")
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/io/test_nba_parsers.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.io.nba'`

- [ ] **Step 3: Implémenter**

`engine/io/nba.py` :

```python
"""Sources NBA : cdn.nba.com (calendrier, scoreboard, box scores live) et
stats.nba.com (effectifs, historique LeagueGameLog, matchups), réservé au
cron local car les IP GitHub y sont bloquées.

Les parseurs sont purs et testés ; NbaSource ajoute l'accès réseau derrière
ApiGuard.
"""
from datetime import date, datetime

import httpx
from nba_api.live.nba.endpoints import BoxScore, ScoreBoard
from nba_api.library import http as _live_http
from nba_api.stats.endpoints import BoxScoreMatchupsV3, CommonTeamRoster, LeagueGameLog
from nba_api.stats.library import http as _stats_http

from engine.io.guard import ApiGuard
from engine.rules.scoring import compute_ttfl_score

SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}

# Akamai refuse les requêtes sans Referer www.nba.com (403) : on l'ajoute aux
# en-têtes de nba_api (live et stats).
_live_http.NBALiveHTTP.headers = {**_live_http.NBALiveHTTP.headers, "Referer": "https://www.nba.com/"}
_stats_http.NBAStatsHTTP.headers = {**_stats_http.NBAStatsHTTP.headers, "Referer": "https://www.nba.com/"}


# --- parseurs purs -------------------------------------------------------

def parse_schedule(payload: dict, start: date, end: date) -> list[dict]:
    rows = []
    for gd in payload.get("leagueSchedule", {}).get("gameDates", []):
        try:
            d = datetime.strptime(gd.get("gameDate", "")[:10], "%m/%d/%Y").date()
        except ValueError:
            continue
        if d < start or d > end:
            continue
        for g in gd.get("games", []):
            if not g.get("gameId"):
                continue
            rows.append({
                "id": g["gameId"],
                "date": d.isoformat(),
                "home_team": (g.get("homeTeam") or {}).get("teamTricode") or "TBD",
                "away_team": (g.get("awayTeam") or {}).get("teamTricode") or "TBD",
                "tip_off": g.get("gameDateTimeUTC") or None,
            })
    return rows


def parse_scoreboard(scoreboard: dict, today: date) -> list[dict]:
    """Le scoreboard live garde parfois la journée NBA précédente active le
    matin (heure de Paris) : on se fie à son propre gameDate."""
    sb_date = today
    if scoreboard.get("gameDate"):
        try:
            sb_date = datetime.strptime(scoreboard["gameDate"], "%Y-%m-%d").date()
        except ValueError:
            sb_date = today
    status_by_code = {3: "final", 2: "live"}
    rows = []
    for g in scoreboard.get("games", []):
        status = status_by_code.get(g.get("gameStatus"), "scheduled")
        played = status != "scheduled"
        rows.append({
            "id": g["gameId"],
            "date": sb_date.isoformat(),
            "home_team": g["homeTeam"]["teamTricode"],
            "away_team": g["awayTeam"]["teamTricode"],
            "tip_off": g.get("gameTimeUTC"),
            "status": status,
            "home_score": (g["homeTeam"].get("score") or 0) if played else None,
            "away_score": (g["awayTeam"].get("score") or 0) if played else None,
        })
    return rows


def _iso_minutes(value: str | None) -> int:
    if not value or "M" not in value:
        return 0
    try:
        return int(value.split("T")[1].split("M")[0])
    except (IndexError, ValueError):
        return 0


def _stat_line(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov) -> dict:
    return {
        "pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk,
        "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta, "tov": tov,
        "ttfl_score": compute_ttfl_score(pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta, tov),
    }


def parse_live_box_score(game: dict, game_date: str) -> list[dict]:
    """Lignes game_logs d'un box score CDN. `game_date` = date US du match
    (games.date) : la date UTC du CDN décale les matchs tardifs d'un jour.
    Les DNP (0 minute) sont gardés : ils alimentent P(joue)."""
    rows = []
    for side, is_home in (("homeTeam", True), ("awayTeam", False)):
        team = game[side]
        for p in team.get("players", []):
            s = p.get("statistics") or {}
            rows.append({
                "player_id": int(p["personId"]),
                "game_id": game["gameId"],
                "date": game_date,
                "team": team["teamTricode"],
                "minutes": _iso_minutes(s.get("minutes")),
                "fouls": s.get("foulsPersonal", 0) or 0,
                "is_home": is_home,
                **_stat_line(
                    s.get("points", 0) or 0, s.get("reboundsTotal", 0) or 0, s.get("assists", 0) or 0,
                    s.get("steals", 0) or 0, s.get("blocks", 0) or 0,
                    s.get("fieldGoalsMade", 0) or 0, s.get("fieldGoalsAttempted", 0) or 0,
                    s.get("threePointersMade", 0) or 0, s.get("threePointersAttempted", 0) or 0,
                    s.get("freeThrowsMade", 0) or 0, s.get("freeThrowsAttempted", 0) or 0,
                    s.get("turnovers", 0) or 0,
                ),
            })
    return rows


def _parse_date(value: str) -> str:
    """LeagueGameLog renvoie « 2025-10-22 » ; PlayerGameLog « OCT 22, 2025 »."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date de match illisible : {value!r}")


def _minutes(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    if ":" in text:
        return int(text.split(":")[0] or 0)
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_league_game_log(rows: list[dict]) -> tuple[dict[str, dict], list[dict], dict[int, dict]]:
    games: dict[str, dict] = {}
    logs: list[dict] = []
    players: dict[int, dict] = {}
    for r in rows:
        team = r["TEAM_ABBREVIATION"]
        matchup = r.get("MATCHUP", "")
        if " vs. " in matchup:
            is_home, other = True, matchup.split(" vs. ")[1].strip()
        else:
            is_home, other = False, matchup.split(" @ ")[-1].strip()
        game_date = _parse_date(str(r["GAME_DATE"]))
        gid = str(r["GAME_ID"])
        games[gid] = {"id": gid, "date": game_date,
                      "home_team": team if is_home else other,
                      "away_team": other if is_home else team, "status": "final"}
        logs.append({
            "player_id": int(r["PLAYER_ID"]), "game_id": gid, "date": game_date, "team": team,
            "minutes": _minutes(r.get("MIN")), "fouls": int(r.get("PF") or 0), "is_home": is_home,
            **_stat_line(int(r["PTS"] or 0), int(r["REB"] or 0), int(r["AST"] or 0), int(r["STL"] or 0),
                         int(r["BLK"] or 0), int(r["FGM"] or 0), int(r["FGA"] or 0), int(r["FG3M"] or 0),
                         int(r["FG3A"] or 0), int(r["FTM"] or 0), int(r["FTA"] or 0), int(r["TOV"] or 0)),
        })
        players[int(r["PLAYER_ID"])] = {"id": int(r["PLAYER_ID"]), "name": r["PLAYER_NAME"], "team": team}
    return games, logs, players


def _short_position(position: str) -> str:
    if "Guard" in position or position in ("G", "G-F"):
        return "G"
    if "Forward" in position or position in ("F", "F-G", "F-C"):
        return "F"
    if "Center" in position or position == "C":
        return "C"
    return "F"


def parse_roster(rows: list[dict], tricode: str) -> list[dict]:
    return [{"id": int(r["PLAYER_ID"]), "name": r["PLAYER"], "team": tricode,
             "position": _short_position(r.get("POSITION") or ""), "active": True} for r in rows]


def parse_matchups(records: list[dict], game_id: str) -> list[dict]:
    return [{
        "game_id": str(r.get("gameId") or game_id),
        "off_team": r.get("teamTricode") or "",
        "off_player_id": int(r["personIdOff"]),
        "off_player_name": f"{r['firstNameOff']} {r['familyNameOff']}",
        "def_player_id": int(r["personIdDef"]),
        "def_player_name": f"{r['firstNameDef']} {r['familyNameDef']}",
        "matchup_seconds": float(r.get("matchupMinutesSort") or 0),
        "partial_possessions": float(r.get("partialPossessions") or 0),
        "player_points": int(r.get("playerPoints") or 0),
        "matchup_assists": int(r.get("matchupAssists") or 0),
        "matchup_turnovers": int(r.get("matchupTurnovers") or 0),
        "matchup_blocks": int(r.get("matchupBlocks") or 0),
        "matchup_fgm": int(r.get("matchupFieldGoalsMade") or 0),
        "matchup_fga": int(r.get("matchupFieldGoalsAttempted") or 0),
        "matchup_tpm": int(r.get("matchupThreePointersMade") or 0),
        "matchup_tpa": int(r.get("matchupThreePointersAttempted") or 0),
        "matchup_ftm": int(r.get("matchupFreeThrowsMade") or 0),
        "matchup_fta": int(r.get("matchupFreeThrowsAttempted") or 0),
    } for r in records]


# --- accès réseau --------------------------------------------------------

class NbaSource:
    def __init__(self, guard: ApiGuard, *, allow_stats: bool = False):
        self.guard = guard
        self.allow_stats = allow_stats

    def _require_stats(self) -> None:
        if not self.allow_stats:
            raise RuntimeError("stats.nba.com réservé au cron local (IP GitHub bloquées)")

    def schedule(self, start: date, end: date) -> list[dict]:
        def fetch():
            resp = httpx.get(SCHEDULE_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        return parse_schedule(self.guard.call("cdn.nba.com", fetch), start, end)

    def scoreboard(self, today: date) -> list[dict]:
        board = self.guard.call("cdn.nba.com", lambda: ScoreBoard().get_dict()["scoreboard"])
        return parse_scoreboard(board, today)

    def box_score(self, game_id: str, game_date: str) -> list[dict]:
        """[] si le CDN a purgé le box score : le cron local le rattrapera via
        LeagueGameLog."""
        try:
            game = self.guard.call("cdn.nba.com", lambda: BoxScore(game_id=game_id).get_dict()["game"])
        except Exception:
            return []
        return parse_live_box_score(game, game_date)

    def league_game_log(self, season: str, season_type: str, date_from: date | None = None):
        self._require_stats()
        kwargs = {"season": season, "season_type_all_star": season_type,
                  "player_or_team_abbreviation": "P", "timeout": 60}
        if date_from is not None:
            kwargs["date_from_nullable"] = date_from.strftime("%m/%d/%Y")
        rows = self.guard.call(
            "stats.nba.com", lambda: LeagueGameLog(**kwargs).get_normalized_dict()["LeagueGameLog"])
        return parse_league_game_log(rows)

    def roster(self, team_id: int, tricode: str) -> list[dict]:
        self._require_stats()
        rows = self.guard.call(
            "stats.nba.com",
            lambda: CommonTeamRoster(team_id=str(team_id), timeout=12).get_normalized_dict()["CommonTeamRoster"],
            is_empty=lambda r: not r,
        )
        return parse_roster(rows, tricode)

    def matchups(self, game_id: str) -> list[dict]:
        self._require_stats()
        records = self.guard.call(
            "stats.nba.com",
            lambda: BoxScoreMatchupsV3(game_id=game_id, timeout=30).player_stats.get_data_frame().to_dict("records"),
            is_empty=lambda r: not r,
        )
        return parse_matchups(records, game_id)
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/io/test_nba_parsers.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/io/nba.py tests/io/test_nba_parsers.py
git commit -m "feat(io): source NBA (parseurs purs, cdn et stats derrière ApiGuard)"
```

---

### Task 6: Blessures ESPN dans `engine/io`

**Files:**
- Move: `sync/injuries.py` → `engine/io/espn.py` ; `tests/test_injuries.py` → `tests/io/test_espn.py`
- Modify: `engine/io/espn.py`, `tests/io/test_espn.py`

**Interfaces:**
- Consumes: `ApiGuard` (tâche 3).
- Produces: `fetch_all_injuries(guard: ApiGuard | None = None, teams=None) -> dict[str, list[dict]]` (même format que l'ancien module), `match_injury_to_player(name, team_players) -> int | None`, `_normalize(name)`.

- [ ] **Step 1: Déplacer le module et son test**

```bash
git mv sync/injuries.py engine/io/espn.py
git mv tests/test_injuries.py tests/io/test_espn.py
sed -i 's/from sync.injuries import/from engine.io.espn import/' tests/io/test_espn.py
```

Note : `sync/main.py` importe encore `sync.injuries`. Le module `sync/` est mort jusqu'à sa suppression en tâche 15 (syncs coupés), et aucun test ne l'importe.

- [ ] **Step 2: Ajouter un test du passage par le garde**

À la fin de `tests/io/test_espn.py` :

```python
from engine.io import espn as espn_module
from engine.io.guard import ApiGuard, HostPolicy


def test_fetch_passe_par_le_garde_et_parse(monkeypatch):
    payload = {"injuries": [{"displayName": "Denver Nuggets", "id": "7", "injuries": [
        {"athlete": {"displayName": "Jamal Murray"}, "status": "Out",
         "details": {"type": "Hamstring", "returnDate": "2026-11-12"},
         "shortComment": "Out 2 semaines", "date": "2026-11-01T12:00Z"}]}]}

    class Resp:
        def raise_for_status(self):
            return self

        def json(self):
            return payload

    monkeypatch.setattr(espn_module.httpx, "get", lambda *a, **k: Resp())
    guard = ApiGuard({"espn": HostPolicy(0.0, 0, 3, 5)})
    result = espn_module.fetch_all_injuries(guard)
    assert result["DEN"][0]["name"] == "Jamal Murray"
    assert result["DEN"][0]["status"] == "Out"
    assert guard.summary()["espn"]["calls"] == 1


def test_fetch_renvoie_vide_si_espn_tombe(monkeypatch):
    def boom(*a, **k):
        raise espn_module.httpx.ConnectError("down")

    monkeypatch.setattr(espn_module.httpx, "get", boom)
    guard = ApiGuard({"espn": HostPolicy(0.0, 0, 3, 5)})
    assert espn_module.fetch_all_injuries(guard) == {}
```

- [ ] **Step 3: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/io/test_espn.py -v`
Expected: FAIL sur `test_fetch_passe_par_le_garde_et_parse` avec `TypeError: fetch_all_injuries() takes from 0 to 1 positional arguments…` ou un résultat sans appel compté.

- [ ] **Step 4: Faire passer l'appel par le garde**

Dans `engine/io/espn.py`, remplacer la signature et le bloc de téléchargement du début de `fetch_all_injuries` (le reste de la fonction ne change pas) :

```python
def fetch_all_injuries(guard=None, teams: list[str] | None = None) -> dict[str, list[dict]]:
    """Blessures de toutes les équipes (endpoint ESPN global, 1 appel).

    Returns {team_tricode: [{"name", "status", "detail", ...}, ...]}, ou {}
    si ESPN est indisponible (le job continue avec les statuts en base).
    """
    def download():
        resp = httpx.get(GLOBAL_INJURIES_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()

    try:
        data = guard.call("espn", download) if guard is not None else download()
    except Exception:
        return {}
```

- [ ] **Step 5: Relancer le test**

Run: `./venv/bin/python -m pytest tests/io/test_espn.py -v`
Expected: PASS (les 8 tests déplacés + 2 nouveaux)

- [ ] **Step 6: Commiter**

```bash
git add engine/io/espn.py tests/io/test_espn.py sync tests
git commit -m "refactor(io): blessures ESPN déplacées dans engine/io, derrière ApiGuard"
```

---

### Task 7: Probabilité de jouer

**Files:**
- Create: `engine/stats/__init__.py`, `engine/stats/availability_prob.py`, `tests/stats/__init__.py`
- Move: `tests/test_dnp_risk.py` → `tests/stats/test_availability_prob.py`

**Interfaces:**
- Produces:
  - `INJURY_PLAY_PROBABILITY`, `HARD_OUT_STATUSES` (frozenset) ;
  - `play_probability(status) -> float` ;
  - `dnp_risk_factor(recent_logs: list[dict]) -> float` (logs `{"minutes": …}`, du plus récent au plus ancien, identique à l'ancien `sync.config`) ;
  - `p_play(*, injury_status, recent_logs, is_b2b_second, exp_minutes) -> float` (soirée du jour) ;
  - `future_p_play(*, injury_status, availability_rate, is_b2b_second, exp_minutes) -> float` (soirées futures) ;
  - constantes `B2B_REST_FACTOR = 0.93`, `B2B_REST_MIN_MINUTES = 30.0`.

- [ ] **Step 1: Déplacer le test existant et ajouter les nouveaux cas**

```bash
mkdir -p tests/stats && touch tests/stats/__init__.py
git mv tests/test_dnp_risk.py tests/stats/test_availability_prob.py
sed -i 's/from sync.config import dnp_risk_factor/from engine.stats.availability_prob import dnp_risk_factor/' tests/stats/test_availability_prob.py
```

Ajouter à la fin de `tests/stats/test_availability_prob.py` :

```python
from engine.stats.availability_prob import future_p_play, p_play, play_probability


def test_play_probability_statuts():
    assert play_probability(None) == 1.0
    assert play_probability("Questionable") == 0.55
    assert play_probability("Out") == 0.0
    assert play_probability("Statut inconnu") == 1.0


def test_p_play_combine_statut_dnp_et_back_to_back():
    logs = [{"minutes": 34}, {"minutes": 33}, {"minutes": 35}]
    assert p_play(injury_status=None, recent_logs=logs, is_b2b_second=False, exp_minutes=34) == 1.0
    assert p_play(injury_status="Questionable", recent_logs=logs, is_b2b_second=True, exp_minutes=34) == 0.55 * 0.93


def test_p_play_back_to_back_sans_effet_pour_un_remplacant():
    logs = [{"minutes": 18}] * 3
    assert p_play(injury_status=None, recent_logs=logs, is_b2b_second=True, exp_minutes=18) == 1.0


def test_future_p_play():
    assert future_p_play(injury_status=None, availability_rate=0.9, is_b2b_second=False, exp_minutes=30) == 0.9
    assert future_p_play(injury_status="Out For Season", availability_rate=0.9,
                         is_b2b_second=False, exp_minutes=30) == 0.0
    assert future_p_play(injury_status=None, availability_rate=1.0, is_b2b_second=True, exp_minutes=36) == 0.93
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/stats/test_availability_prob.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.stats'`

- [ ] **Step 3: Implémenter**

`engine/stats/__init__.py` : vide.

`engine/stats/availability_prob.py` :

```python
"""P(joue) : statut ESPN, motif DNP récent, repos de back-to-back.

La fuite n°1 de 2025-26 (audit §9) : 17 zéros sur 162 picks. Un zéro coûte
la soirée ET bloque le joueur (R7), d'où une P(joue) aussi honnête que possible.
"""

# Probabilité de jouer selon le statut ESPN (observation empirique TTFL).
INJURY_PLAY_PROBABILITY = {
    "Out": 0.00,
    "Out For Season": 0.00,
    "Suspended": 0.00,
    "Doubtful": 0.20,
    "Questionable": 0.55,
    "Day-To-Day": 0.65,
    "Game-Time Decision": 0.55,
    "Probable": 0.85,
}

# Statuts qui retirent le joueur des candidats du soir.
HARD_OUT_STATUSES = frozenset({"Out", "Doubtful", "Out For Season", "Suspended"})

# 2e soir d'un back-to-back : les gros minutages sont parfois mis au repos
# (load management). À recalibrer par backtest (L2).
B2B_REST_FACTOR = 0.93
B2B_REST_MIN_MINUTES = 30.0


def play_probability(status: str | None) -> float:
    if not status:
        return 1.0
    return INJURY_PLAY_PROBABILITY.get(status, 1.0)


def dnp_risk_factor(recent_logs: list[dict]) -> float:
    """Pénalité pour un motif DNP que le flux ESPN n'a pas encore reflété.
    `recent_logs` du plus récent au plus ancien, avec la clé minutes."""
    if not recent_logs:
        return 1.0
    last3 = recent_logs[:3]
    dnp = sum(1 for log in last3 if (log.get("minutes") or 0) == 0)
    if len(last3) < 3:
        return 0.55 if dnp == len(last3) and dnp >= 1 else 1.0
    if dnp == 3:
        return 0.30
    if dnp == 2:
        return 0.55
    if dnp == 1:
        return 0.75 if (last3[0].get("minutes") or 0) == 0 else 0.90
    return 1.0


def _b2b(is_b2b_second: bool, exp_minutes: float) -> float:
    return B2B_REST_FACTOR if is_b2b_second and exp_minutes >= B2B_REST_MIN_MINUTES else 1.0


def p_play(*, injury_status: str | None, recent_logs: list[dict],
           is_b2b_second: bool, exp_minutes: float) -> float:
    return play_probability(injury_status) * dnp_risk_factor(recent_logs) * _b2b(is_b2b_second, exp_minutes)


def future_p_play(*, injury_status: str | None, availability_rate: float,
                  is_b2b_second: bool, exp_minutes: float) -> float:
    """Soirées futures : le statut du jour ne dit presque rien d'un match dans
    10 jours, sauf une saison terminée. On prend le taux de présence récent."""
    if injury_status == "Out For Season":
        return 0.0
    return availability_rate * _b2b(is_b2b_second, exp_minutes)
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/stats/test_availability_prob.py -v`
Expected: PASS (les 9 tests déplacés + 4 nouveaux)

- [ ] **Step 5: Commiter**

```bash
git add engine/stats tests/stats tests
git commit -m "feat(stats): probabilité de jouer (statut, DNP, back-to-back)"
```

---

### Task 8: Profil joueur et prior d'intersaison (S6)

**Files:**
- Create: `engine/stats/profile.py`, `tests/stats/test_profile.py`

**Interfaces:**
- Produces:
  - `GameLog(player_id, game_id, date, season, team, minutes, ttfl, is_home)` (frozen) ;
  - `GameLog.from_row(row: dict) -> GameLog` (ligne `game_logs` de Supabase) ;
  - `PlayerProfile(player_id, ttfl_per_min, exp_minutes, games_current, stddev, availability_rate)`, avec la propriété `base = ttfl_per_min × exp_minutes` ;
  - `role_scales(prior_minutes: dict[int, float], rosters: dict[str, list[int]]) -> dict[str, float]` ;
  - `prior_minutes(prior_logs: list[GameLog]) -> dict[int, float]` ;
  - `build_profile(player_id, current_logs, prior_logs, role_scale=1.0) -> PlayerProfile` ;
  - constantes `PRIOR_K = 10`, `ROOKIE_TTFL_PER_MIN = 0.55`, `ROOKIE_MINUTES = 12.0`.

- [ ] **Step 1: Écrire le test**

`tests/stats/test_profile.py` :

```python
from datetime import date, timedelta

import pytest

from engine.stats.profile import (
    GameLog, PRIOR_K, ROOKIE_MINUTES, ROOKIE_TTFL_PER_MIN, build_profile, prior_minutes, role_scales,
)


def _logs(pid, season, pairs, start=date(2026, 11, 30)):
    """pairs = [(minutes, ttfl)] du plus récent au plus ancien."""
    return [GameLog(pid, f"g{season}{i}", start - timedelta(days=2 * i), season, "DEN", m, t, True)
            for i, (m, t) in enumerate(pairs)]


def test_rookie_sans_historique():
    p = build_profile(9, [], [])
    assert (p.ttfl_per_min, p.exp_minutes, p.games_current) == (ROOKIE_TTFL_PER_MIN, ROOKIE_MINUTES, 0)


def test_debut_de_saison_prior_seul_avec_echelle_de_role():
    prior = _logs(1, "2025-26", [(30, 45), (30, 45)])
    p = build_profile(1, [], prior, role_scale=1.1)
    assert p.ttfl_per_min == pytest.approx(1.5)
    assert p.exp_minutes == pytest.approx(33.0)
    assert p.base == pytest.approx(49.5)


def test_melange_prior_et_saison_courante():
    prior = _logs(1, "2025-26", [(30, 30)] * 5)            # 1.0 TTFL/min, 30 min
    current = _logs(1, "2026-27", [(36, 72)] * PRIOR_K)    # 2.0 TTFL/min, 36 min
    p = build_profile(1, current, prior)
    assert p.ttfl_per_min == pytest.approx(1.5)            # w = 10 / (10 + 10)
    assert p.exp_minutes == pytest.approx(33.0)


def test_dnp_exclus_de_l_efficacite_mais_comptes_dans_la_presence():
    current = _logs(1, "2026-27", [(0, 0), (30, 60), (0, 0), (30, 60)])
    p = build_profile(1, current, [])
    w = 2 / (2 + PRIOR_K)
    assert p.ttfl_per_min == pytest.approx(w * 2.0 + (1 - w) * ROOKIE_TTFL_PER_MIN)
    assert p.availability_rate == pytest.approx(0.5)


def test_recence_le_match_recent_pese_plus():
    hot = build_profile(1, _logs(1, "2026-27", [(30, 90), (30, 30)]), [])
    cold = build_profile(1, _logs(1, "2026-27", [(30, 30), (30, 90)]), [])
    assert hot.ttfl_per_min > cold.ttfl_per_min


def test_presence_bornee():
    current = _logs(1, "2026-27", [(0, 0)] * 5 + [(30, 30)])
    assert build_profile(1, current, []).availability_rate == 0.5


def test_role_scales():
    minutes = {1: 36.0, 2: 34.0, 3: 30.0}
    rosters = {
        "DEN": [1, 2, 3] + list(range(10, 17)),   # 7 joueurs à 20 min → 100 + 140 = 240
        "BOS": [1, 2, 3],                          # 100 min : la star est partie → plafonné à 1.15
        "LAL": list(range(20, 30)),                # 10 × 30 min = 300 : encombré → plancher 0.85
    }
    minutes.update({i: 20.0 for i in range(10, 17)})
    minutes.update({i: 30.0 for i in range(20, 30)})
    scales = role_scales(minutes, rosters)
    assert scales["DEN"] == pytest.approx(1.0)
    assert scales["BOS"] == 1.15
    assert scales["LAL"] == 0.85


def test_prior_minutes_moyenne_des_matchs_joues():
    logs = _logs(1, "2025-26", [(30, 40), (0, 0), (34, 50)])
    assert prior_minutes(logs) == {1: 32.0}
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/stats/test_profile.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.stats.profile'`

- [ ] **Step 3: Implémenter**

`engine/stats/profile.py` :

```python
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
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/stats/test_profile.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/stats/profile.py tests/stats/test_profile.py
git commit -m "feat(stats): profil joueur et prior d'intersaison fondu (S6)"
```

---

### Task 9: Facteurs défensifs par poste

**Files:**
- Create: `engine/stats/team_defense.py`, `tests/stats/test_team_defense.py`

**Interfaces:**
- Consumes: `GameLog` (tâche 8).
- Produces:
  - `defense_factors(current_logs, prior_logs, games: dict[str, dict], positions: dict[int, str]) -> dict[str, dict[str, float]]` : équipe → poste (`"G"`, `"F"`, `"C"`) → facteur borné [0,85 ; 1,15] ;
  - `opp_factor(factors, opponent, position) -> float` (1,0 si inconnu) ;
  - constantes `PRIOR_GAMES = 15`, `PRIOR_REGRESSION = 0.5`.

- [ ] **Step 1: Écrire le test**

`tests/stats/test_team_defense.py` :

```python
from datetime import date

import pytest

from engine.stats.profile import GameLog
from engine.stats.team_defense import defense_factors, opp_factor

GAMES = {"g1": {"home_team": "DEN", "away_team": "LAL"},
         "g2": {"home_team": "BOS", "away_team": "LAL"}}
POS = {1: "G", 2: "G", 3: "C"}


def _log(pid, gid, team, minutes, ttfl, season="2026-27"):
    return GameLog(pid, gid, date(2026, 11, 1), season, team, minutes, ttfl, team == GAMES[gid]["home_team"])


def test_equipe_qui_encaisse_plus_que_la_moyenne():
    # Les meneurs font 1.5 TTFL/min contre LAL (g1), 0.5 contre BOS (g2) ; moyenne ligue 1.0.
    current = [_log(1, "g1", "DEN", 30, 45), _log(2, "g2", "LAL", 30, 15)]
    f = defense_factors(current, [], GAMES, POS)
    # Sans prior, le facteur courant est fondu vers 1.0 : w = 1 / (1 + 15)
    w = 1 / 16
    assert f["LAL"]["G"] == pytest.approx(w * 1.5 + (1 - w) * 1.0)
    assert f["BOS"]["G"] == pytest.approx(w * 0.5 + (1 - w) * 1.0)


def test_prior_regresse_de_moitie_et_borne():
    prior = [_log(1, "g1", "DEN", 30, 90, "2025-26"), _log(2, "g2", "LAL", 30, 10, "2025-26")]
    f = defense_factors([], prior, GAMES, POS)
    # ratio prior LAL = 3.0/1.667 = 1.8 → régressé 1.4 → borné 1.15
    assert f["LAL"]["G"] == 1.15
    # ratio prior BOS = 0.333/1.667 = 0.2 → régressé 0.6 → borné 0.85
    assert f["BOS"]["G"] == 0.85


def test_log_d_une_equipe_absente_du_match_ignore():
    current = [_log(1, "g1", "DEN", 30, 45), GameLog(3, "g1", date(2026, 11, 1), "2026-27", "PHX", 30, 99, True)]
    f = defense_factors(current, [], GAMES, POS)
    assert "C" not in f.get("DEN", {}) or f["DEN"]["C"] == 1.0


def test_opp_factor_inconnu_neutre():
    assert opp_factor({}, "XXX", "G") == 1.0
    assert opp_factor({"LAL": {"G": 1.1}}, "LAL", "G-F") == 1.0
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/stats/test_team_defense.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.stats.team_defense'`

- [ ] **Step 3: Implémenter**

`engine/stats/team_defense.py` :

```python
"""Facteur défensif par poste : TTFL par minute concédé par l'équipe au
poste, rapporté à la moyenne de la ligue. L'adversaire se lit dans
game_logs.team (équipe au moment du match), ce qui corrige l'attribution
erronée après transferts (audit §2).

Saison en cours fondue avec la saison précédente régressée de moitié vers
1.0 (effectifs changés, S6). Borné à [0.85, 1.15].
"""
from collections import defaultdict

from engine.stats.profile import GameLog

POSITIONS = ("G", "F", "C")
PRIOR_GAMES = 15
PRIOR_REGRESSION = 0.5
FACTOR_BOUNDS = (0.85, 1.15)


def _clamp(value: float) -> float:
    return max(FACTOR_BOUNDS[0], min(FACTOR_BOUNDS[1], value))


def _allowed(logs: list[GameLog], games: dict[str, dict], positions: dict[int, str]):
    totals: dict[str, dict[str, list[float]]] = defaultdict(lambda: {p: [0.0, 0.0] for p in POSITIONS})
    game_count: dict[str, set[str]] = defaultdict(set)
    for log in logs:
        game = games.get(log.game_id)
        if not game or log.minutes <= 0:
            continue
        if log.team == game["home_team"]:
            opponent = game["away_team"]
        elif log.team == game["away_team"]:
            opponent = game["home_team"]
        else:
            continue
        pos = positions.get(log.player_id, "F")
        pos = pos if pos in POSITIONS else "F"
        totals[opponent][pos][0] += log.ttfl
        totals[opponent][pos][1] += log.minutes
        game_count[opponent].add(log.game_id)
    return totals, game_count


def _league(totals) -> dict[str, float]:
    league = {}
    for pos in POSITIONS:
        ttfl = sum(t[pos][0] for t in totals.values())
        minutes = sum(t[pos][1] for t in totals.values())
        league[pos] = ttfl / minutes if minutes > 0 else 0.0
    return league


def defense_factors(current_logs: list[GameLog], prior_logs: list[GameLog],
                    games: dict[str, dict], positions: dict[int, str]) -> dict[str, dict[str, float]]:
    cur, cur_games = _allowed(current_logs, games, positions)
    pri, _ = _allowed(prior_logs, games, positions)
    league_cur, league_pri = _league(cur), _league(pri)
    factors: dict[str, dict[str, float]] = {}
    for team in set(cur) | set(pri):
        n = len(cur_games.get(team, ()))
        weight = n / (n + PRIOR_GAMES)
        factors[team] = {}
        for pos in POSITIONS:
            ttfl, minutes = cur[team][pos] if team in cur else (0.0, 0.0)
            f_cur = (ttfl / minutes) / league_cur[pos] if minutes > 0 and league_cur[pos] > 0 else 1.0
            ttfl_p, minutes_p = pri[team][pos] if team in pri else (0.0, 0.0)
            if minutes_p > 0 and league_pri[pos] > 0:
                f_pri = 1.0 + PRIOR_REGRESSION * ((ttfl_p / minutes_p) / league_pri[pos] - 1.0)
            else:
                f_pri = 1.0
            factors[team][pos] = _clamp(weight * f_cur + (1 - weight) * f_pri)
    return factors


def opp_factor(factors: dict[str, dict[str, float]], opponent: str, position: str) -> float:
    return factors.get(opponent, {}).get(position, 1.0)
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/stats/test_team_defense.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/stats/team_defense.py tests/stats/test_team_defense.py
git commit -m "feat(stats): facteurs défensifs par poste, par saison avec prior régressé"
```

---

### Task 10: Projection, repos et agrégats pour le front

**Files:**
- Create: `engine/stats/projection.py`, `engine/stats/aggregates.py`, `tests/stats/test_projection.py`, `tests/stats/test_aggregates.py`

**Interfaces:**
- Consumes: `PlayerProfile`, `GameLog` (tâche 8).
- Produces:
  - `GameContext(opponent: str, is_home: bool, rest_days: int | None, opp_factor: float)` (frozen) ;
  - `project(profile, ctx) -> float` ;
  - `rest_days(team, night, team_dates: dict[str, list[date]]) -> int | None` ;
  - `HOME_FACTOR = 1.02`, `AWAY_FACTOR = 0.98`, `B2B_FACTOR = 0.96` ;
  - `player_aggregates(logs: list[GameLog]) -> dict` avec les clés `avg_ttfl_l5, avg_ttfl_l10, avg_ttfl_l20, avg_ttfl_season, stddev_ttfl, home_avg, away_avg, avg_minutes_l10`.

- [ ] **Step 1: Écrire les tests**

`tests/stats/test_projection.py` :

```python
from datetime import date

import pytest

from engine.stats.profile import PlayerProfile
from engine.stats.projection import GameContext, project, rest_days

PROFILE = PlayerProfile(1, ttfl_per_min=1.5, exp_minutes=34.0, games_current=20, stddev=8.0, availability_rate=0.95)


def test_projection_domicile_defense_faible():
    ctx = GameContext("WAS", is_home=True, rest_days=1, opp_factor=1.10)
    assert project(PROFILE, ctx) == pytest.approx(51.0 * 1.10 * 1.02)


def test_projection_exterieur_back_to_back():
    ctx = GameContext("BOS", is_home=False, rest_days=0, opp_factor=0.90)
    assert project(PROFILE, ctx) == pytest.approx(51.0 * 0.90 * 0.98 * 0.96)


def test_rest_days():
    dates = {"DEN": [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 5)]}
    assert rest_days("DEN", date(2026, 11, 2), dates) == 0
    assert rest_days("DEN", date(2026, 11, 5), dates) == 2
    assert rest_days("DEN", date(2026, 11, 1), dates) is None
    assert rest_days("LAL", date(2026, 11, 1), dates) is None
```

`tests/stats/test_aggregates.py` :

```python
from datetime import date, timedelta

from engine.stats.aggregates import player_aggregates
from engine.stats.profile import GameLog


def _log(i, minutes, ttfl, home):
    return GameLog(1, f"g{i}", date(2026, 12, 1) - timedelta(days=i), "2026-27", "DEN", minutes, ttfl, home)


def test_aggregats_ignorent_les_dnp():
    logs = [_log(0, 0, 0, True)] + [_log(i, 30, 40, i % 2 == 0) for i in range(1, 11)]
    a = player_aggregates(logs)
    assert a["avg_ttfl_l5"] == 40.0 and a["avg_ttfl_season"] == 40.0
    assert a["avg_minutes_l10"] == 30.0


def test_split_domicile_exterieur_avec_garde_d_echantillon():
    logs = [_log(1, 30, 50, True), _log(2, 30, 30, False), _log(3, 30, 40, False)]
    a = player_aggregates(logs)
    assert a["home_avg"] == a["avg_ttfl_season"]        # < 4 matchs : repli sur la moyenne


def test_aggregats_vides():
    assert player_aggregates([])["avg_ttfl_season"] == 0
```

- [ ] **Step 2: Lancer les tests pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/stats/test_projection.py tests/stats/test_aggregates.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.stats.projection'`

- [ ] **Step 3: Implémenter**

`engine/stats/projection.py` :

```python
"""Projection TTFL d'un joueur pour un match : base du profil (efficacité ×
minutes de rôle) × adversaire × terrain × fatigue.

Facteurs volontairement peu nombreux : le facteur de tendance historique
était inversé (audit §3) et redondant avec la pondération de récence du
profil ; le split domicile/extérieur individuel est remplacé par un effet
terrain fixe (split individuel trop bruité, et compté deux fois).
"""
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

from engine.stats.profile import PlayerProfile

HOME_FACTOR = 1.02
AWAY_FACTOR = 0.98
B2B_FACTOR = 0.96


@dataclass(frozen=True)
class GameContext:
    opponent: str
    is_home: bool
    rest_days: int | None
    opp_factor: float


def project(profile: PlayerProfile, ctx: GameContext) -> float:
    terrain = HOME_FACTOR if ctx.is_home else AWAY_FACTOR
    fatigue = B2B_FACTOR if ctx.rest_days == 0 else 1.0
    return profile.base * ctx.opp_factor * terrain * fatigue


def rest_days(team: str, night: date, team_dates: dict[str, list[date]]) -> int | None:
    """Jours de repos avant `night` (0 = 2e soir d'un back-to-back). None si
    aucun match antérieur connu. `team_dates` triées par date."""
    dates = team_dates.get(team, [])
    i = bisect_left(dates, night)
    if i == 0:
        return None
    return (night - dates[i - 1]).days - 1
```

`engine/stats/aggregates.py` :

```python
"""Colonnes players.avg_* lues par le front actuel (listes, fiches joueur),
calculées sur la saison en cours (DNP exclus)."""
from statistics import mean, pstdev

from engine.stats.profile import GameLog

MIN_SPLIT_GAMES = 4
EMPTY = {"avg_ttfl_l5": 0, "avg_ttfl_l10": 0, "avg_ttfl_l20": 0, "avg_ttfl_season": 0,
         "stddev_ttfl": 0, "home_avg": 0, "away_avg": 0, "avg_minutes_l10": 0}


def player_aggregates(logs: list[GameLog]) -> dict:
    played = sorted((l for l in logs if l.minutes > 0), key=lambda l: l.date, reverse=True)
    if not played:
        return dict(EMPTY)
    scores = [l.ttfl for l in played]
    season = mean(scores)
    home = [l.ttfl for l in played if l.is_home]
    away = [l.ttfl for l in played if not l.is_home]
    return {
        "avg_ttfl_l5": mean(scores[:5]),
        "avg_ttfl_l10": mean(scores[:10]),
        "avg_ttfl_l20": mean(scores[:20]),
        "avg_ttfl_season": season,
        "stddev_ttfl": pstdev(scores) if len(scores) >= 3 else 0,
        "home_avg": mean(home) if len(home) >= MIN_SPLIT_GAMES else season,
        "away_avg": mean(away) if len(away) >= MIN_SPLIT_GAMES else season,
        "avg_minutes_l10": mean(l.minutes for l in played[:10]),
    }
```

- [ ] **Step 4: Relancer les tests**

Run: `./venv/bin/python -m pytest tests/stats -v`
Expected: PASS

- [ ] **Step 5: Commiter**

```bash
git add engine/stats/projection.py engine/stats/aggregates.py tests/stats/test_projection.py tests/stats/test_aggregates.py
git commit -m "feat(stats): projection d'un match, repos, agrégats joueurs"
```

---

### Task 11: Valeur S1 et planificateur

**Files:**
- Create: `engine/strategy/__init__.py`, `engine/strategy/value.py`, `engine/strategy/planner.py`, `tests/strategy/__init__.py`, `tests/strategy/test_value.py`, `tests/strategy/test_planner.py`

**Interfaces:**
- Consumes: `COOLDOWN_DAYS` (`engine.rules.availability`), `GameContext` (tâche 10).
- Produces:
  - `FUTURE_DECAY = 0.985` ; `discount(days_ahead) -> float` ;
  - `lock_value(future: list[tuple[int, float]]) -> float` (liste de (jours d'avance, espérance), maximum décoté sur 1 ≤ k < COOLDOWN_DAYS) ;
  - `tonight_value(p_play, projection, lock) -> float` ; `future_value(days_ahead, p_play, projection) -> float` ;
  - `Cell(player_id: int, night: date, projection: float, p_play: float, value: float, ctx: GameContext)` (frozen) ;
  - `solve(cells: list[Cell], nights: list[date]) -> dict[date, Cell]` ; `TOP_PER_NIGHT = 40`.

- [ ] **Step 1: Écrire les tests**

`tests/strategy/__init__.py` : vide.

`tests/strategy/test_value.py` :

```python
import pytest

from engine.strategy.value import discount, future_value, lock_value, tonight_value


def test_discount():
    assert discount(0) == 1.0
    assert discount(10) == pytest.approx(0.985 ** 10)


def test_lock_value_meilleur_futur_decote_dans_la_fenetre():
    future = [(3, 40.0), (20, 60.0), (30, 90.0), (0, 99.0)]
    assert lock_value(future) == pytest.approx(max(0.985 ** 3 * 40, 0.985 ** 20 * 60))


def test_lock_value_sans_futur():
    assert lock_value([]) == 0.0


def test_tonight_value_exemple_s1():
    # Star à 60 % de jouer (50 projetés) contre joueur fiable (98 %, 40) :
    # le zéro possible gaspille aussi son blocage de 30 jours.
    star = tonight_value(0.6, 50.0, lock=45.0)
    fiable = tonight_value(0.98, 40.0, lock=30.0)
    assert star == pytest.approx(30.0 - 18.0)
    assert fiable == pytest.approx(39.2 - 0.6)
    assert fiable > star


def test_future_value():
    assert future_value(10, 0.9, 50.0) == pytest.approx(0.985 ** 10 * 45.0)
```

`tests/strategy/test_planner.py` :

```python
from datetime import date, timedelta

from engine.stats.projection import GameContext
from engine.strategy.planner import TOP_PER_NIGHT, Cell, solve

D0 = date(2026, 11, 1)
CTX = GameContext("XXX", True, 1, 1.0)


def _cell(pid, day, value):
    return Cell(pid, D0 + timedelta(days=day), value, 1.0, value, CTX)


def test_match_facile_a_j20_fait_jouer_un_autre_joueur_ce_soir():
    # X : 40 ce soir, 60 à J+20. Y : 38 ce soir. Jouer X ce soir le bloque pour J+20.
    cells = [_cell(1, 0, 40.0), _cell(1, 20, 60.0), _cell(2, 0, 38.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=20)])
    assert plan[D0].player_id == 2
    assert plan[D0 + timedelta(days=20)].player_id == 1


def test_un_joueur_au_plus_une_fois():
    cells = [_cell(1, 0, 50.0), _cell(1, 1, 50.0), _cell(2, 1, 10.0)]
    plan = solve(cells, [D0, D0 + timedelta(days=1)])
    assert {c.player_id for c in plan.values()} == {1, 2}


def test_soiree_sans_candidat_absente_du_plan():
    plan = solve([_cell(1, 0, 50.0)], [D0, D0 + timedelta(days=1)])
    assert list(plan) == [D0]


def test_elagage_garde_les_meilleurs_par_soiree():
    cells = [_cell(pid, 0, float(pid)) for pid in range(TOP_PER_NIGHT + 10)]
    plan = solve(cells, [D0])
    assert plan[D0].player_id == TOP_PER_NIGHT + 9


def test_plan_vide():
    assert solve([], []) == {}
```

- [ ] **Step 2: Lancer les tests pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/strategy -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.strategy'`

- [ ] **Step 3: Implémenter**

`engine/strategy/__init__.py` : vide.

`engine/strategy/value.py` :

```python
"""Espérance complète d'un pick (S1) et décote du futur (S2).

Picker un joueur le bloque 30 jours (R3), qu'il joue ou non (R7). S'il ne
joue pas, ce blocage est perdu pour rien : on retire donc
(1 − P(joue)) × lock_value, où lock_value est la meilleure espérance future
du joueur dans la fenêtre de cooldown, décotée par l'incertitude.
"""
from engine.rules.availability import COOLDOWN_DAYS

FUTURE_DECAY = 0.985  # par jour d'avance ; à calibrer par backtest (L2)


def discount(days_ahead: int) -> float:
    return FUTURE_DECAY ** days_ahead


def lock_value(future: list[tuple[int, float]]) -> float:
    values = [discount(k) * ev for k, ev in future if 1 <= k < COOLDOWN_DAYS]
    return max(values, default=0.0)


def tonight_value(p_play: float, projection: float, lock: float) -> float:
    return p_play * projection - (1.0 - p_play) * lock


def future_value(days_ahead: int, p_play: float, projection: float) -> float:
    return discount(days_ahead) * p_play * projection
```

`engine/strategy/planner.py` :

```python
"""Affectation joueurs × soirées sur l'horizon (S2).

Horizon = 30 jours = une fenêtre de cooldown (J+30) : « chaque joueur au
plus une fois » est exactement la règle R3. Problème d'affectation résolu
par linear_sum_assignment (algorithme hongrois).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import linear_sum_assignment

from engine.stats.projection import GameContext

TOP_PER_NIGHT = 40          # candidats gardés par soirée (matrice gérable)
_SENTINEL = 1e9             # coût d'une case impossible


@dataclass(frozen=True)
class Cell:
    player_id: int
    night: date
    projection: float
    p_play: float
    value: float
    ctx: GameContext


def solve(cells: list[Cell], nights: list[date]) -> dict[date, Cell]:
    if not cells or not nights:
        return {}
    wanted = set(nights)
    by_night: dict[date, list[Cell]] = defaultdict(list)
    for c in cells:
        if c.night in wanted:
            by_night[c.night].append(c)
    kept = [c for night_cells in by_night.values()
            for c in sorted(night_cells, key=lambda c: c.value, reverse=True)[:TOP_PER_NIGHT]]
    if not kept:
        return {}
    players = sorted({c.player_id for c in kept})
    row = {pid: i for i, pid in enumerate(players)}
    col = {d: j for j, d in enumerate(nights)}
    cost = np.full((len(players), len(nights)), _SENTINEL)
    best: dict[tuple[int, date], Cell] = {}
    for c in kept:
        key = (c.player_id, c.night)
        if key not in best or c.value > best[key].value:
            best[key] = c
            cost[row[c.player_id], col[c.night]] = -c.value
    rows, cols = linear_sum_assignment(cost)
    plan = {}
    for r, j in zip(rows, cols):
        if cost[r, j] >= _SENTINEL:
            continue
        plan[nights[j]] = best[(players[r], nights[j])]
    return dict(sorted(plan.items()))
```

- [ ] **Step 4: Relancer les tests**

Run: `./venv/bin/python -m pytest tests/strategy -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/strategy tests/strategy
git commit -m "feat(strategy): valeur S1 et planificateur 30 jours"
```

---

### Task 12: Décision SR et argumentaires

**Files:**
- Create: `engine/strategy/regular.py`, `engine/explain/__init__.py`, `engine/explain/texts.py`, `tests/strategy/test_regular.py`, `tests/strategy/test_texts.py`

**Interfaces:**
- Consumes: `Night` (`engine.rules.calendar`) ; `is_available`, `PickRow`, `SecondChance`, `SeriesRow`, `COOLDOWN_DAYS` (`engine.rules.availability`) ; `is_eligible` ; `PlayerProfile` ; `GameContext`, `project`, `rest_days` ; `opp_factor` ; `p_play`, `future_p_play`, `HARD_OUT_STATUSES` ; `Cell`, `solve` ; `lock_value`, `tonight_value`, `future_value`.
- Produces:
  - `HORIZON_DAYS = 30`, `MIN_EXP_MINUTES = 15.0`, `TOP_RECOMMENDATIONS = 50` ;
  - `DecisionInputs(today, nights, games, players, profiles, recent_logs, defense, picks, second_chances, series)` avec :
    - `games` : dicts `id, date (str ISO), home_team, away_team, game_type`, fenêtre qui inclut les 5 jours passés pour le repos ;
    - `players` : `dict[int, dict]` (lignes `players`) ;
    - `recent_logs` : `dict[int, list[dict]]`, logs `{"minutes"}` du plus récent au plus ancien ;
  - `Recommendation(cell: Cell, lock_value: float, locked_until: date, best_future: Cell | None)` ;
  - `Decision(tonight: date | None, recommendations: list[Recommendation], plan: dict[date, Cell])` ;
  - `decide(inputs) -> Decision` ;
  - `engine.explain.texts` :
    - `tier(rank) -> str` ;
    - `reco_texts(rec, rank, player_name) -> tuple[list[str], list[str], str, list[str]]` (pros, cons, verdict, tags) ;
    - `plan_explanation(cell) -> str` ;
    - `describe_night(cell) -> str`.

- [ ] **Step 1: Écrire les tests**

`tests/strategy/test_regular.py` :

```python
from datetime import date, datetime, timedelta

from engine.rules.availability import PickRow
from engine.rules.calendar import PARIS, Night
from engine.stats.profile import PlayerProfile
from engine.strategy.regular import DecisionInputs, decide

TODAY = date(2026, 11, 2)


def _night(d, n=1):
    return Night(d, "2026-27", "regular", n, datetime(d.year, d.month, d.day, 23, tzinfo=PARIS), False)


def _game(gid, d, home, away, gtype="regular"):
    return {"id": gid, "date": d.isoformat(), "home_team": home, "away_team": away, "game_type": gtype}


def _prof(pid, eff=1.5, minutes=34.0):
    return PlayerProfile(pid, eff, minutes, 10, 8.0, 0.95)


PLAYERS = {
    1: {"id": 1, "name": "Star DEN", "team": "DEN", "position": "C", "injury_status": None, "active": True},
    2: {"id": 2, "name": "Guard LAL", "team": "LAL", "position": "G", "injury_status": None, "active": True},
    3: {"id": 3, "name": "Bench DEN", "team": "DEN", "position": "F", "injury_status": None, "active": True},
}


def _inputs(**over):
    base = dict(
        today=TODAY,
        nights=[_night(TODAY), _night(TODAY + timedelta(days=20))],
        games=[_game("g1", TODAY, "DEN", "LAL"), _game("g2", TODAY + timedelta(days=20), "DEN", "WAS")],
        players=PLAYERS,
        profiles={1: _prof(1), 2: _prof(2, eff=1.2), 3: _prof(3, eff=1.0, minutes=10.0)},
        recent_logs={1: [{"minutes": 34}] * 3, 2: [{"minutes": 33}] * 3, 3: [{"minutes": 10}] * 3},
        defense={"WAS": {"C": 1.15}},
        picks=[], second_chances=[], series=[],
    )
    base.update(over)
    return DecisionInputs(**base)


def test_decide_reco_du_soir_triee_par_valeur_et_filtre_minutes():
    d = decide(_inputs())
    assert d.tonight == TODAY
    ids = [r.cell.player_id for r in d.recommendations]
    assert 3 not in ids                       # 10 min attendues < 15
    assert ids == sorted(ids, key=lambda pid: -next(r.cell.value for r in d.recommendations if r.cell.player_id == pid))


def test_decide_lock_value_et_meilleur_futur():
    d = decide(_inputs())
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.best_future is not None and star.best_future.night == TODAY + timedelta(days=20)
    assert star.lock_value > 0
    assert star.locked_until == TODAY + timedelta(days=30)


def test_decide_plan_joue_la_star_a_son_meilleur_soir():
    d = decide(_inputs())
    assert d.plan[TODAY + timedelta(days=20)].player_id == 1
    assert d.plan[TODAY].player_id == 2


def test_decide_exclut_cooldown_et_out():
    players = {**PLAYERS, 2: {**PLAYERS[2], "injury_status": "Out"}}
    picks = [PickRow(9, 1, TODAY - timedelta(days=10), "regular", "2026-27")]
    d = decide(_inputs(players=players, picks=picks))
    assert [r.cell.player_id for r in d.recommendations] == []


def test_decide_respecte_les_reservations():
    resa = PickRow(7, 1, TODAY + timedelta(days=20), "regular", "2026-27")
    d = decide(_inputs(picks=[resa]))
    assert TODAY + timedelta(days=20) not in d.plan          # soirée déjà fixée
    assert 1 not in [r.cell.player_id for r in d.recommendations]   # réservé à J+20 → bloqué ce soir


def test_decide_debut_de_saison_utilise_le_prior():
    # Profil issu du prior seul (0 match courant) : projection > 0 (bug B5).
    profiles = {1: PlayerProfile(1, 1.4, 32.0, 0, 0.0, 0.9), 2: _prof(2), 3: _prof(3)}
    d = decide(_inputs(profiles=profiles))
    star = next(r for r in d.recommendations if r.cell.player_id == 1)
    assert star.cell.projection > 40


def test_decide_pas_de_reco_un_soir_sans_match():
    d = decide(_inputs(nights=[_night(TODAY + timedelta(days=20))]))
    assert d.tonight is None and d.recommendations == []


def test_decide_ignore_matchs_ineligibles():
    games = [_game("p1", TODAY, "DEN", "LAL", "preseason")]
    d = decide(_inputs(games=games, nights=[_night(TODAY)]))
    assert d.recommendations == []
```

`tests/strategy/test_texts.py` :

```python
from datetime import date

from engine.explain.texts import describe_night, plan_explanation, reco_texts, tier
from engine.stats.projection import GameContext
from engine.strategy.planner import Cell
from engine.strategy.regular import Recommendation


def _cell(night, is_home=True, rest=1, opp=1.1, p=0.98):
    return Cell(1, night, 50.0, p, 48.0, GameContext("WAS", is_home, rest, opp))


def test_tier():
    assert [tier(r) for r in (1, 10, 11, 25, 26)] == ["elite", "elite", "solid", "solid", "filler"]


def test_reco_texts_domicile_et_blocage():
    rec = Recommendation(_cell(date(2026, 11, 2)), 40.0, date(2026, 12, 2), _cell(date(2026, 11, 20), is_home=False))
    pros, cons, verdict, tags = reco_texts(rec, 1, "Nikola Jokic")
    assert any("domicile" in p for p in pros)
    assert any("02/12" in c for c in cons)
    assert "Jokic" in verdict
    assert "home" in tags and "reco_du_soir" in tags


def test_reco_texts_risques():
    rec = Recommendation(_cell(date(2026, 11, 2), rest=0, opp=0.9, p=0.55), 0.0, date(2026, 12, 2), None)
    pros, cons, _, tags = reco_texts(rec, 30, "X")
    assert any("back-to-back" in c for c in cons)
    assert any("55 %" in c for c in cons)
    assert "b2b" in tags and "dnp_risk" in tags


def test_describe_et_plan_explanation():
    c = _cell(date(2026, 11, 20), is_home=False)
    assert describe_night(c) == "vendredi 20/11 @ WAS"
    assert "50" in plan_explanation(c)
```

- [ ] **Step 2: Lancer les tests pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/strategy/test_regular.py tests/strategy/test_texts.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.strategy.regular'`

- [ ] **Step 3: Implémenter la décision**

`engine/strategy/regular.py` :

```python
"""Décision du soir et plan 30 jours (S1, S2).

Reco du soir (L1) = best-available trié par valeur S1. Le plan est indicatif
jusqu'à sa validation par backtest (L2, règle d'activation de la spec §7).
Les règles de disponibilité viennent de engine.rules : en PO, le même
calcul applique automatiquement le pick-and-drop et les éliminations (la
stratégie PO dédiée arrive en L3).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.rules.availability import COOLDOWN_DAYS, PickRow, SecondChance, SeriesRow, is_available
from engine.rules.calendar import Night
from engine.rules.game_types import is_eligible
from engine.stats.availability_prob import HARD_OUT_STATUSES, future_p_play, p_play
from engine.stats.profile import PlayerProfile
from engine.stats.projection import GameContext, project, rest_days
from engine.stats.team_defense import opp_factor
from engine.strategy.planner import Cell, solve
from engine.strategy.value import future_value, lock_value, tonight_value

HORIZON_DAYS = 30
MIN_EXP_MINUTES = 15.0
TOP_RECOMMENDATIONS = 50


@dataclass
class DecisionInputs:
    today: date
    nights: list[Night]
    games: list[dict]
    players: dict[int, dict]
    profiles: dict[int, PlayerProfile]
    recent_logs: dict[int, list[dict]]
    defense: dict[str, dict[str, float]]
    picks: list[PickRow]
    second_chances: list[SecondChance] = field(default_factory=list)
    series: list[SeriesRow] = field(default_factory=list)


@dataclass(frozen=True)
class Recommendation:
    cell: Cell
    lock_value: float
    locked_until: date
    best_future: Cell | None


@dataclass
class Decision:
    tonight: date | None
    recommendations: list[Recommendation]
    plan: dict[date, Cell]


def _game_date(g: dict) -> date:
    d = g["date"]
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def decide(inputs: DecisionInputs) -> Decision:
    today = inputs.today
    nights = {n.date: n for n in inputs.nights
              if not n.is_phantom and n.n_eligible_games > 0 and 0 <= (n.date - today).days < HORIZON_DAYS}

    team_dates: dict[str, list[date]] = defaultdict(list)
    games_by_night: dict[date, list[dict]] = defaultdict(list)
    for g in inputs.games:
        d = _game_date(g)
        team_dates[g["home_team"]].append(d)
        team_dates[g["away_team"]].append(d)
        if d in nights and is_eligible(g.get("game_type", "unknown")):
            games_by_night[d].append(g)
    for dates in team_dates.values():
        dates.sort()

    roster: dict[str, list[int]] = defaultdict(list)
    for pid, row in inputs.players.items():
        if row.get("active", True):
            roster[row["team"]].append(pid)

    raw = []  # (days_ahead, player_id, night, projection, p, ctx)
    for d, night in nights.items():
        k = (d - today).days
        for g in games_by_night[d]:
            for team, opponent, is_home in ((g["home_team"], g["away_team"], True),
                                            (g["away_team"], g["home_team"], False)):
                for pid in roster.get(team, []):
                    profile = inputs.profiles.get(pid)
                    if profile is None or profile.exp_minutes < MIN_EXP_MINUTES:
                        continue
                    row = inputs.players[pid]
                    status = row.get("injury_status")
                    if k == 0 and status in HARD_OUT_STATUSES:
                        continue
                    if not is_available(player_id=pid, player_team=team, night=d, season=night.season,
                                        mode=night.mode, picks=inputs.picks,
                                        second_chances=inputs.second_chances, series=inputs.series).ok:
                        continue
                    rd = rest_days(team, d, team_dates)
                    ctx = GameContext(opponent, is_home, rd,
                                      opp_factor(inputs.defense, opponent, row.get("position", "F")))
                    projection = project(profile, ctx)
                    b2b = rd == 0
                    if k == 0:
                        p = p_play(injury_status=status, recent_logs=inputs.recent_logs.get(pid, []),
                                   is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
                    else:
                        p = future_p_play(injury_status=status, availability_rate=profile.availability_rate,
                                          is_b2b_second=b2b, exp_minutes=profile.exp_minutes)
                    raw.append((k, pid, d, projection, p, ctx))

    future_ev: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for k, pid, _d, projection, p, _ctx in raw:
        if k > 0:
            future_ev[pid].append((k, p * projection))

    cells: list[Cell] = []
    for k, pid, d, projection, p, ctx in raw:
        if k == 0:
            value = tonight_value(p, projection, lock_value(future_ev[pid]))
        else:
            value = future_value(k, p, projection)
        cells.append(Cell(pid, d, projection, p, value, ctx))

    fixed = {p.date for p in inputs.picks}
    plan_nights = sorted(d for d in nights if d not in fixed)
    plan = solve([c for c in cells if c.night in set(plan_nights)], plan_nights)

    tonight = today if today in nights else None
    recommendations: list[Recommendation] = []
    if tonight is not None:
        future_cells: dict[int, list[Cell]] = defaultdict(list)
        for c in cells:
            if c.night != today:
                future_cells[c.player_id].append(c)
        tonight_cells = sorted((c for c in cells if c.night == today), key=lambda c: c.value, reverse=True)
        for c in tonight_cells[:TOP_RECOMMENDATIONS]:
            best = max(future_cells[c.player_id], key=lambda f: f.value, default=None)
            recommendations.append(Recommendation(
                cell=c, lock_value=lock_value(future_ev[c.player_id]),
                locked_until=today + timedelta(days=COOLDOWN_DAYS), best_future=best))
    return Decision(tonight, recommendations, plan)
```

- [ ] **Step 4: Implémenter les argumentaires**

`engine/explain/__init__.py` : vide.

`engine/explain/texts.py` :

```python
"""Argumentaires FR (saison régulière) des recommandations et du plan."""
from engine.strategy.planner import Cell

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def tier(rank: int) -> str:
    if rank <= 10:
        return "elite"
    return "solid" if rank <= 25 else "filler"


def describe_night(cell: Cell) -> str:
    sep = "vs" if cell.ctx.is_home else "@"
    return f"{_JOURS[cell.night.weekday()]} {cell.night:%d/%m} {sep} {cell.ctx.opponent}"


def reco_texts(rec, rank: int, player_name: str) -> tuple[list[str], list[str], str, list[str]]:
    c = rec.cell
    pros: list[str] = []
    cons: list[str] = []
    tags: list[str] = []
    if c.ctx.is_home:
        pros.append("🏠 Match à domicile")
        tags.append("home")
    else:
        cons.append("✈️ Match à l'extérieur")
    delta = round((c.ctx.opp_factor - 1.0) * 100)
    if delta >= 5:
        pros.append(f"🎯 Défense adverse faible à son poste (+{delta} %)")
    elif delta <= -5:
        cons.append(f"🛡️ Défense adverse solide à son poste ({delta} %)")
    if c.ctx.rest_days == 0:
        cons.append("😴 2e soir d'un back-to-back")
        tags.append("b2b")
    elif c.ctx.rest_days is not None and c.ctx.rest_days >= 2:
        pros.append(f"🔋 {c.ctx.rest_days} jours de repos")
    if c.p_play < 0.95:
        cons.append(f"⚠️ Risque d'absence : {round(c.p_play * 100)} % de chances de jouer")
        tags.append("dnp_risk")
    else:
        pros.append(f"✅ {round(c.p_play * 100)} % de chances de jouer")
    blocage = f"🔒 Le jouer ce soir le bloque jusqu'au {rec.locked_until:%d/%m}"
    if rec.best_future is not None:
        blocage += f" (meilleur soir à venir : {describe_night(rec.best_future)}, {rec.best_future.projection:.0f} pts projetés)"
    cons.append(blocage)
    if rank <= 3:
        tags.append("reco_du_soir")
    verdict = (f"{player_name} : {c.projection:.0f} pts projetés, valeur {c.value:.1f} "
               f"une fois le risque d'absence et le blocage de 30 jours pris en compte.")
    return pros, cons, verdict, tags


def plan_explanation(cell: Cell) -> str:
    return (f"{describe_night(cell)} · {cell.projection:.0f} pts projetés · "
            f"{round(cell.p_play * 100)} % de chances de jouer")
```

- [ ] **Step 5: Relancer les tests**

Run: `./venv/bin/python -m pytest tests/strategy -v`
Expected: PASS (tâche 11 + 8 + 4 nouveaux)

Note : `describe_night` pour le 20/11/2026 renvoie `vendredi 20/11 @ WAS`, car le 20 novembre 2026 tombe un vendredi.

- [ ] **Step 6: Commiter**

```bash
git add engine/strategy/regular.py engine/explain tests/strategy/test_regular.py tests/strategy/test_texts.py
git commit -m "feat(strategy): décision SR (S1 + plan 30 j) et argumentaires"
```

---

### Task 13: Job `daily_sync`

**Files:**
- Create: `engine/jobs/__init__.py`, `engine/jobs/daily_sync.py`, `tests/jobs/__init__.py`, `tests/jobs/fakes.py`, `tests/jobs/test_daily_sync.py`

**Interfaces:**
- Consumes: `SupabaseRepo` (interface, tâche 4), `NbaSource` (`schedule`, `scoreboard`, `box_score`, tâche 5), `fetch_all_injuries`, `match_injury_to_player` (tâche 6), `build_nights` (L1a), `season_for_date`, `previous_season` (tâche 2), stats (tâches 7-10), `decide`, `texts` (tâche 12).
- Produces:
  - `RunResult(players_updated: int, recommendations: int, plan_nights: int, warnings: list[str])` ;
  - `run(repo, source, fetch_injuries, today, now) -> RunResult` ;
  - `main()` (point d'entrée `python -m engine.jobs.daily_sync`) ;
  - `tests/jobs/fakes.py` : `FakeRepo` (mêmes méthodes que `SupabaseRepo`, en mémoire) et `FakeNbaSource`.

- [ ] **Step 1: Écrire les faux et le test**

`tests/jobs/__init__.py` : vide.

`tests/jobs/fakes.py` :

```python
"""Faux repo et fausses sources, en mémoire, pour tester les jobs sans réseau."""
from datetime import date


def _d(v):
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


class FakeRepo:
    def __init__(self, players=(), games=(), logs=(), picks=(), series=(), second_chances=()):
        self.players = {p["id"]: dict(p) for p in players}
        self.games = {g["id"]: dict(g) for g in games}
        self.logs = {(l["player_id"], l["game_id"]): dict(l) for l in logs}
        self.picks = [dict(p) for p in picks]
        self.series = list(series)
        self.second_chances = list(second_chances)
        self.nights = []
        self.recommendations = {}
        self.plan = []
        self.matchups = []
        self.inactive = set()

    # lectures
    def load_players(self):
        return list(self.players.values())

    def load_games_between(self, start, end):
        return [g for g in self.games.values() if start <= _d(g["date"]) <= end]

    def load_games_of_seasons(self, seasons):
        return [g for g in self.games.values() if g.get("season") in seasons]

    def load_game_logs(self, seasons):
        return [l for l in self.logs.values() if l.get("season") in seasons]

    def load_series(self, season):
        return [s for s in self.series if s.get("season") == season]

    def load_picks(self, season):
        return [p for p in self.picks if p.get("season") == season]

    def load_second_chances(self):
        return list(self.second_chances)

    def game_ids_with_logs(self, game_ids):
        return {gid for (_, gid) in self.logs} & set(game_ids)

    def game_ids_with_matchups(self, game_ids):
        return {m["game_id"] for m in self.matchups} & set(game_ids)

    # écritures
    def upsert_games(self, rows):
        from engine.rules.game_types import game_type_of, season_of
        for r in rows:
            g = {**self.games.get(r["id"], {"status": "scheduled"}), **r}
            g["game_type"] = game_type_of(g["id"])
            g["season"] = season_of(g["id"], _d(g["date"]))
            self.games[r["id"]] = g

    def upsert_players(self, rows):
        for r in rows:
            self.players[r["id"]] = {**self.players.get(r["id"], {"active": True}), **r}

    def upsert_game_logs(self, rows):
        for r in rows:
            missing = r["player_id"] not in self.players
            assert not missing, f"FK game_logs.player_id violée : {r['player_id']}"
            g = self.games[r["game_id"]]
            self.logs[(r["player_id"], r["game_id"])] = {**r, "season": g["season"]}

    def upsert_matchups_raw(self, rows):
        self.matchups.extend(rows)

    def set_inactive(self, ids):
        for pid in ids:
            self.players[pid]["active"] = False
            self.inactive.add(pid)

    def set_pick_score(self, pick_id, score):
        next(p for p in self.picks if p["id"] == pick_id)["actual_score"] = score

    def replace_nights(self, start, rows):
        self.nights = [n for n in self.nights if _d(n["date"]) < start] + list(rows)

    def replace_recommendations(self, night, rows):
        self.recommendations[night] = list(rows)

    def write_plan(self, rows, keep_since):
        self.plan = list(rows)


class FakeNbaSource:
    def __init__(self, schedule=(), scoreboard=(), box_scores=None, fail=False):
        self._schedule = list(schedule)
        self._scoreboard = list(scoreboard)
        self._box = box_scores or {}
        self.fail = fail

    def _maybe_fail(self):
        if self.fail:
            raise ConnectionError("NBA indisponible")

    def schedule(self, start, end):
        self._maybe_fail()
        return [g for g in self._schedule if start <= _d(g["date"]) <= end]

    def scoreboard(self, today):
        self._maybe_fail()
        return list(self._scoreboard)

    def box_score(self, game_id, game_date):
        self._maybe_fail()
        return list(self._box.get(game_id, []))
```

`tests/jobs/test_daily_sync.py` :

```python
from datetime import UTC, date, datetime, timedelta

from engine.jobs.daily_sync import run
from tests.jobs.fakes import FakeNbaSource, FakeRepo

TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


def _player(pid, team, pos="G", **k):
    return {"id": pid, "name": f"Joueur {pid}", "team": team, "position": pos,
            "injury_status": None, "active": True, **k}


def _log(pid, gid, d, team, minutes=34, ttfl=50, season="2026-27", home=True):
    return {"player_id": pid, "game_id": gid, "date": d.isoformat(), "season": season, "team": team,
            "minutes": minutes, "ttfl_score": ttfl, "is_home": home}


def _base_repo(**over):
    players = [_player(1, "DEN", "C"), _player(2, "LAL"), _player(3, "BOS")]
    past = TODAY - timedelta(days=2)
    games = [
        {"id": "0022600010", "date": past.isoformat(), "home_team": "DEN", "away_team": "LAL",
         "status": "final", "game_type": "regular", "season": "2026-27"},
        {"id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "BOS",
         "away_team": "DEN", "status": "final", "game_type": "regular", "season": "2026-27"},
    ]
    logs = [_log(1, "0022600010", past, "DEN"), _log(2, "0022600010", past, "LAL", ttfl=35, home=False)]
    # Saison précédente : sans prior, un seul match courant laisse le profil
    # proche du rookie (< 15 min attendues) et personne ne serait candidat.
    for pid, team in ((1, "DEN"), (2, "LAL"), (3, "BOS")):
        logs += [_log(pid, f"prior{pid}{i}", date(2026, 3, 1) + timedelta(days=i), team, season="2025-26")
                 for i in range(5)]
    picks = [{"id": 1, "player_id": 3, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(),
              "mode": "regular", "season": "2026-27", "actual_score": None, "is_x2": False}]
    kwargs = dict(players=players, games=games, logs=logs, picks=picks)
    kwargs.update(over)
    return FakeRepo(**kwargs)


SCHEDULE = [
    {"id": "0022600020", "date": TODAY.isoformat(), "home_team": "DEN", "away_team": "LAL",
     "tip_off": "2026-11-03T01:00:00Z"},
    {"id": "0012600099", "date": (TODAY + timedelta(days=1)).isoformat(), "home_team": "BOS",
     "away_team": "LAL", "tip_off": None},
    {"id": "0022600021", "date": (TODAY + timedelta(days=5)).isoformat(), "home_team": "BOS",
     "away_team": "DEN", "tip_off": None},
]

BOX = {"0022600011": [
    {"player_id": 3, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "team": "BOS",
     "minutes": 36, "ttfl_score": 44, "is_home": True, "pts": 30, "reb": 5, "ast": 5, "stl": 1, "blk": 0,
     "fgm": 10, "fga": 20, "tpm": 3, "tpa": 8, "ftm": 7, "fta": 8, "tov": 2, "fouls": 2},
    {"player_id": 999, "game_id": "0022600011", "date": (TODAY - timedelta(days=1)).isoformat(), "team": "BOS",
     "minutes": 5, "ttfl_score": 2, "is_home": True, "pts": 2, "reb": 0, "ast": 0, "stl": 0, "blk": 0,
     "fgm": 1, "fga": 1, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, "tov": 0, "fouls": 0},
]}


def test_daily_sync_de_bout_en_bout():
    repo = _base_repo()
    result = run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: {}, TODAY, NOW)
    # soirées : ce soir et J+5 ; la présaison de J+1 n'est pas une soirée
    assert [n["date"] for n in repo.nights] == [TODAY.isoformat(), (TODAY + timedelta(days=5)).isoformat()]
    # box score ingéré et pick scoré
    assert repo.picks[0]["actual_score"] == 44
    # recos du soir écrites, avec les colonnes S1
    recs = repo.recommendations[TODAY]
    assert result.recommendations == len(recs) > 0
    assert {"projection", "p_play", "value", "lock_value", "locked_until", "best_future",
            "estimated_score", "rank", "tier", "pros", "cons", "verdict", "tags"} <= set(recs[0])
    assert recs[0]["rank"] == 1
    assert repo.plan and all(r["generated_at"] == NOW.isoformat() for r in repo.plan)


def test_daily_sync_ignore_logs_de_joueurs_inconnus():
    repo = _base_repo()
    result = run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: {}, TODAY, NOW)
    assert (999, "0022600011") not in repo.logs
    assert any("inconnu" in w for w in result.warnings)


def test_daily_sync_continue_si_nba_indisponible():
    repo = _base_repo()
    repo.upsert_games(SCHEDULE)          # calendrier déjà en base
    result = run(repo, FakeNbaSource(fail=True), lambda: {}, TODAY, NOW)
    assert result.warnings                # étapes réseau notées, pas d'exception
    assert repo.recommendations[TODAY]   # la décision tourne sur les données en base


def test_daily_sync_blessures():
    repo = _base_repo()
    injuries = {"LAL": [{"name": "Joueur 2", "status": "Out", "detail": "Genou", "return_date": None,
                         "short_comment": "", "updated_at": ""}]}
    run(repo, FakeNbaSource(schedule=SCHEDULE, box_scores=BOX), lambda: injuries, TODAY, NOW)
    assert repo.players[2]["injury_status"] == "Out"
    assert 2 not in [r["player_id"] for r in repo.recommendations[TODAY]]
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/jobs/test_daily_sync.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.jobs'`

- [ ] **Step 3: Implémenter**

`engine/jobs/__init__.py` : vide.

`engine/jobs/daily_sync.py` :

```python
"""Job quotidien (GitHub Actions, 4×/jour) : calendrier, scores, box scores,
blessures, soirées, recommandations du soir et plan 30 jours.

Jamais d'appel à stats.nba.com (IP GitHub bloquées). Chaque étape réseau
peut échouer sans faire tomber le job : la décision tourne alors sur les
données en base, et l'échec est noté dans `warnings`.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from engine.explain.texts import plan_explanation, reco_texts, tier
from engine.io.espn import match_injury_to_player
from engine.rules.availability import PickRow, SecondChance, SeriesRow
from engine.rules.calendar import PARIS, build_nights
from engine.rules.game_types import is_eligible, previous_season, season_for_date
from engine.stats.aggregates import player_aggregates
from engine.stats.profile import GameLog, build_profile, prior_minutes, role_scales
from engine.stats.team_defense import defense_factors
from engine.strategy.regular import HORIZON_DAYS, DecisionInputs, decide

SCHEDULE_PAST_DAYS = 5
SCHEDULE_AHEAD_DAYS = 35
BOX_SCORE_DAYS = 3
PLAN_RETENTION = timedelta(days=7)
IDENTITY = ("id", "name", "team", "position")


@dataclass
class RunResult:
    players_updated: int = 0
    recommendations: int = 0
    plan_nights: int = 0
    warnings: list[str] = field(default_factory=list)


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _step(name: str, fn, result: RunResult):
    try:
        return fn()
    except Exception as exc:  # réseau, disjoncteur, budget : on continue
        result.warnings.append(f"{name} : {type(exc).__name__} {exc}")
        return None


def _ingest_box_scores(repo, source, today: date, known_players: set[int], result: RunResult) -> None:
    recent = [g for g in repo.load_games_between(today - timedelta(days=BOX_SCORE_DAYS), today - timedelta(days=1))
              if is_eligible(g.get("game_type", "unknown"))]
    done = repo.game_ids_with_logs(g["id"] for g in recent)
    for g in recent:
        if g["id"] in done:
            continue
        rows = _step(f"box score {g['id']}", lambda g=g: source.box_score(g["id"], str(g["date"])[:10]), result) or []
        unknown = [r for r in rows if r["player_id"] not in known_players]
        if unknown:
            result.warnings.append(f"box score {g['id']} : {len(unknown)} joueur(s) inconnu(s) ignoré(s)")
        rows = [r for r in rows if r["player_id"] in known_players]
        if rows:
            repo.upsert_game_logs(rows)


def _score_picks(repo, season: str, today: date) -> None:
    games = {g["id"]: g for g in repo.load_games_between(today - timedelta(days=40), today)}
    picks = [p for p in repo.load_picks(season) if p.get("actual_score") is None and _d(p["date"]) < today]
    logs = {(l["player_id"], l["game_id"]): l for l in repo.load_game_logs([season])}
    with_logs = {gid for (_, gid) in logs}
    for p in picks:
        log = logs.get((p["player_id"], p["game_id"]))
        if log is not None:
            repo.set_pick_score(p["id"], int(log["ttfl_score"]))
        elif games.get(p["game_id"], {}).get("status") == "final" and p["game_id"] in with_logs:
            repo.set_pick_score(p["id"], 0)   # R7 : ne pas avoir joué = 0


def _apply_injuries(repo, injuries: dict[str, list[dict]]) -> None:
    players = repo.load_players()
    by_team: dict[str, list[dict]] = defaultdict(list)
    for p in players:
        by_team[p["team"]].append(p)
    injured: dict[int, dict] = {}
    for team, entries in injuries.items():
        for inj in entries:
            pid = match_injury_to_player(inj["name"], by_team.get(team, []))
            if pid is not None:
                injured[pid] = inj
    rows = []
    for p in players:
        inj = injured.get(p["id"])
        if inj is not None:
            rows.append({**{k: p[k] for k in IDENTITY}, "injury_status": inj["status"],
                         "injury_detail": inj.get("detail"), "injury_short_comment": inj.get("short_comment"),
                         "injury_return_date": inj.get("return_date"), "injury_updated_at": inj.get("updated_at")})
        elif p.get("injury_status"):
            rows.append({**{k: p[k] for k in IDENTITY}, "injury_status": None, "injury_detail": None,
                         "injury_short_comment": None, "injury_return_date": None})
    if rows:
        repo.upsert_players(rows)


def run(repo, source, fetch_injuries, today: date, now: datetime) -> RunResult:
    result = RunResult()
    season = season_for_date(today)
    prior = previous_season(season)

    schedule = _step("calendrier", lambda: source.schedule(
        today - timedelta(days=SCHEDULE_PAST_DAYS), today + timedelta(days=SCHEDULE_AHEAD_DAYS)), result)
    if schedule:
        repo.upsert_games(schedule)
    board = _step("scoreboard", lambda: source.scoreboard(today), result)
    if board:
        repo.upsert_games(board)          # après le calendrier : le statut live/final gagne

    known = {p["id"] for p in repo.load_players()}
    _ingest_box_scores(repo, source, today, known, result)
    _score_picks(repo, season, today)

    injuries = _step("blessures", fetch_injuries, result)
    if injuries:
        _apply_injuries(repo, injuries)

    players = {p["id"]: p for p in repo.load_players()}
    season_games = {g["id"]: g for g in repo.load_games_of_seasons([season, prior])}
    all_logs = [GameLog.from_row(r) for r in repo.load_game_logs([season, prior])]
    current_by_player: dict[int, list[GameLog]] = defaultdict(list)
    prior_by_player: dict[int, list[GameLog]] = defaultdict(list)
    for log in all_logs:
        (current_by_player if log.season == season else prior_by_player)[log.player_id].append(log)

    rosters: dict[str, list[int]] = defaultdict(list)
    for pid, p in players.items():
        if p.get("active", True):
            rosters[p["team"]].append(pid)
    scales = role_scales(prior_minutes([l for l in all_logs if l.season == prior]), rosters)
    profiles = {pid: build_profile(pid, current_by_player[pid], prior_by_player[pid], scales.get(p["team"], 1.0))
                for pid, p in players.items() if p.get("active", True)}
    defense = defense_factors([l for l in all_logs if l.season == season], [l for l in all_logs if l.season == prior],
                              season_games, {pid: p.get("position", "F") for pid, p in players.items()})

    aggregate_rows = [{**{k: p[k] for k in IDENTITY}, **player_aggregates(current_by_player[pid])}
                      for pid, p in players.items() if current_by_player[pid]]
    if aggregate_rows:
        repo.upsert_players(aggregate_rows)
    result.players_updated = len(aggregate_rows)

    window = repo.load_games_between(today - timedelta(days=SCHEDULE_PAST_DAYS), today + timedelta(days=SCHEDULE_AHEAD_DAYS))
    series_rows = repo.load_series(season)
    nights = [n for n in build_nights([g for g in window if _d(g["date"]) >= today], series_rows)]
    repo.replace_nights(today, [{"date": n.date.isoformat(), "season": n.season, "mode": n.mode,
                                 "n_eligible_games": n.n_eligible_games, "closing_at": n.closing_at.isoformat(),
                                 "is_phantom": n.is_phantom, "updated_at": now.isoformat()} for n in nights])

    recent_logs = {pid: [{"minutes": l.minutes} for l in sorted(logs, key=lambda l: l.date, reverse=True)[:5]]
                   for pid, logs in current_by_player.items()}
    picks = [PickRow(p["id"], p["player_id"], _d(p["date"]), p["mode"], p["season"]) for p in repo.load_picks(season)]
    second_chances = [SecondChance(s["pick_id"], s["player_id"], _d(s["bought_on"]), _d(s["expires_on"]))
                      for s in repo.load_second_chances()]
    series = [SeriesRow(s["season"], s["round"], s["home_team"], s["away_team"],
                        s.get("home_wins") or 0, s.get("away_wins") or 0, s["status"]) for s in series_rows]
    decision = decide(DecisionInputs(today=today, nights=nights, games=window, players=players,
                                     profiles=profiles, recent_logs=recent_logs, defense=defense,
                                     picks=picks, second_chances=second_chances, series=series))

    if decision.tonight is not None:
        rows = []
        for rank, rec in enumerate(decision.recommendations, start=1):
            pros, cons, verdict, tags = reco_texts(rec, rank, players[rec.cell.player_id]["name"])
            rows.append({
                "date": today.isoformat(), "player_id": rec.cell.player_id, "rank": rank,
                "estimated_score": round(rec.cell.p_play * rec.cell.projection, 1),
                "perf_score": round(rec.cell.projection, 1), "matchup_score": round(rec.cell.ctx.opp_factor, 3),
                "strategy_score": round(rec.cell.value, 1),
                "projection": round(rec.cell.projection, 1), "p_play": round(rec.cell.p_play, 3),
                "value": round(rec.cell.value, 1), "lock_value": round(rec.lock_value, 1),
                "locked_until": rec.locked_until.isoformat(),
                "best_future": None if rec.best_future is None else plan_explanation(rec.best_future),
                "pros": pros, "cons": cons, "verdict": verdict, "tier": tier(rank), "tags": tags,
                "computed_at": now.isoformat(),
            })
        repo.replace_recommendations(today, rows)
        result.recommendations = len(rows)

    plan_rows = [{"generated_at": now.isoformat(), "night": night.isoformat(), "player_id": c.player_id,
                  "is_x2": False, "projection": round(c.projection, 1), "p_play": round(c.p_play, 3),
                  "value": round(c.value, 1), "explanation": plan_explanation(c)}
                 for night, c in decision.plan.items() if (night - today).days < HORIZON_DAYS]
    repo.write_plan(plan_rows, keep_since=now - PLAN_RETENTION)
    result.plan_nights = len(plan_rows)
    return result


def main() -> None:
    from engine.io.espn import fetch_all_injuries
    from engine.io.guard import ApiGuard
    from engine.io.nba import NbaSource
    from engine.io.repo import SupabaseRepo

    guard = ApiGuard()
    repo = SupabaseRepo.from_env()
    source = NbaSource(guard, allow_stats=False)
    now = datetime.now(UTC)
    today = now.astimezone(PARIS).date()
    log_id = repo.start_log("daily_sync")
    try:
        result = run(repo, source, lambda: fetch_all_injuries(guard), today, now)
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    repo.finish_log(log_id, status="success", players_updated=result.players_updated, api_calls=guard.summary())
    print(f"daily_sync {today} : {result.recommendations} recos, plan {result.plan_nights} soirées, "
          f"{len(result.warnings)} avertissement(s)")
    for w in result.warnings:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/jobs/test_daily_sync.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Lancer la suite complète**

Run: `SUPABASE_URL=http://localhost SUPABASE_KEY=test SUPABASE_SERVICE_KEY=test TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commiter**

```bash
git add engine/jobs tests/jobs
git commit -m "feat(jobs): daily_sync (calendrier, box scores, blessures, soirées, recos S1, plan)"
```

---

### Task 14: Job `local_nightly`

**Files:**
- Create: `engine/jobs/local_nightly.py`, `tests/jobs/test_local_nightly.py`
- Modify: `tests/jobs/fakes.py` (ajout de `FakeStatsSource`)

**Interfaces:**
- Consumes: `NbaSource.roster`, `league_game_log`, `matchups` (tâche 5), `FakeRepo` (tâche 13), `season_for_date`, `is_eligible`.
- Produces:
  - `run(repo, nba, today, teams, backfill_season=None) -> list[str]` (avertissements) ;
  - `to_raw_matchups(rows, game) -> list[dict]` ;
  - `main()` (`python -m engine.jobs.local_nightly [--backfill-season 2025-26]`).

- [ ] **Step 1: Écrire le faux et le test**

Ajouter à `tests/jobs/fakes.py` :

```python
class FakeStatsSource:
    def __init__(self, rosters=None, game_logs=None, matchups=None, fail_teams=()):
        self._rosters = rosters or {}
        self._logs = game_logs or {}
        self._matchups = matchups or {}
        self.fail_teams = set(fail_teams)
        self.log_calls = []

    def roster(self, team_id, tricode):
        if tricode in self.fail_teams:
            raise ConnectionError("roster KO")
        return list(self._rosters.get(tricode, []))

    def league_game_log(self, season, season_type, date_from=None):
        self.log_calls.append((season, season_type, date_from))
        return self._logs.get((season, season_type), ({}, [], {}))

    def matchups(self, game_id):
        return list(self._matchups.get(game_id, []))
```

`tests/jobs/test_local_nightly.py` :

```python
from datetime import date, timedelta

from engine.jobs.local_nightly import run
from tests.jobs.fakes import FakeRepo, FakeStatsSource

TODAY = date(2026, 11, 2)
TEAMS = [{"id": 1, "abbreviation": "DEN"}, {"id": 2, "abbreviation": "LAL"}]


def _roster(pid, team):
    return {"id": pid, "name": f"J{pid}", "team": team, "position": "G", "active": True}


def test_effectifs_et_desactivation_des_joueurs_coupes():
    repo = FakeRepo(players=[{"id": 9, "name": "Coupé", "team": "DEN", "position": "F", "active": True}])
    nba = FakeStatsSource(rosters={"DEN": [_roster(1, "DEN")], "LAL": [_roster(2, "LAL")]})
    run(repo, nba, TODAY, TEAMS)
    assert repo.players[1]["team"] == "DEN" and repo.players[2]["active"] is True
    assert repo.players[9]["active"] is False


def test_pas_de_desactivation_si_un_effectif_manque():
    repo = FakeRepo(players=[{"id": 9, "name": "Coupé", "team": "DEN", "position": "F", "active": True}])
    nba = FakeStatsSource(rosters={"DEN": [_roster(1, "DEN")]}, fail_teams={"LAL"})
    warnings = run(repo, nba, TODAY, TEAMS)
    assert repo.players[9]["active"] is True
    assert any("LAL" in w for w in warnings)


def test_historique_saison_courante_depuis_j_moins_3():
    game = {"0022600010": {"id": "0022600010", "date": "2026-10-31", "home_team": "DEN",
                           "away_team": "LAL", "status": "final"}}
    logs = [{"player_id": 5, "game_id": "0022600010", "date": "2026-10-31", "team": "DEN", "minutes": 30,
             "ttfl_score": 40, "is_home": True, "pts": 20, "reb": 5, "ast": 5, "stl": 1, "blk": 1,
             "fgm": 8, "fga": 15, "tpm": 2, "tpa": 5, "ftm": 2, "fta": 2, "tov": 1, "fouls": 2}]
    players = {5: {"id": 5, "name": "Nouveau", "team": "DEN"}}
    nba = FakeStatsSource(game_logs={("2026-27", "Regular Season"): (game, logs, players)})
    repo = FakeRepo()
    run(repo, nba, TODAY, [])
    assert nba.log_calls == [("2026-27", "Regular Season", TODAY - timedelta(days=3))]
    assert repo.players[5]["active"] is False and repo.players[5]["position"] == "F"
    assert (5, "0022600010") in repo.logs


def test_backfill_saison_complete_regular_et_playoffs():
    nba = FakeStatsSource()
    run(FakeRepo(), nba, TODAY, [], backfill_season="2025-26")
    assert nba.log_calls == [("2025-26", "Regular Season", None), ("2025-26", "Playoffs", None)]


def test_matchups_bruts_des_matchs_eligibles_termines():
    games = [{"id": "0022600010", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "DEN",
              "away_team": "LAL", "status": "final", "game_type": "regular", "season": "2026-27", "series_id": None},
             {"id": "0012600001", "date": (TODAY - timedelta(days=1)).isoformat(), "home_team": "DEN",
              "away_team": "LAL", "status": "final", "game_type": "preseason", "season": "2026-27", "series_id": None}]
    row = {"game_id": "0022600010", "off_team": "DEN", "off_player_id": 1, "off_player_name": "A",
           "def_player_id": 2, "def_player_name": "B", "matchup_seconds": 300.0, "partial_possessions": 10.0,
           "player_points": 8, "matchup_assists": 1, "matchup_turnovers": 0, "matchup_blocks": 0,
           "matchup_fgm": 3, "matchup_fga": 6, "matchup_tpm": 1, "matchup_tpa": 2, "matchup_ftm": 1, "matchup_fta": 1}
    repo = FakeRepo(games=games)
    run(repo, FakeStatsSource(matchups={"0022600010": [row], "0012600001": [row]}), TODAY, [])
    assert [(m["game_id"], m["def_team"]) for m in repo.matchups] == [("0022600010", "LAL")]
```

- [ ] **Step 2: Lancer le test pour constater l'échec**

Run: `./venv/bin/python -m pytest tests/jobs/test_local_nightly.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'engine.jobs.local_nightly'`

- [ ] **Step 3: Implémenter**

`engine/jobs/local_nightly.py` :

```python
"""Job local (PC, cron 23h50) : tout ce qui passe par stats.nba.com, dont les
IP GitHub sont bloquées.

- effectifs des 30 équipes (+ désactivation des joueurs coupés, seulement si
  les 30 effectifs ont répondu) ;
- historique de la saison via LeagueGameLog (1 appel pour toute la ligue),
  qui rattrape les box scores purgés du CDN ;
- matchups bruts défenseur/joueur des matchs éligibles terminés.

`--backfill-season 2025-26` : charge une saison complète (SR + PO), une fois.
"""
import argparse
from datetime import UTC, date, datetime, timedelta

from engine.rules.calendar import PARIS
from engine.rules.game_types import is_eligible, season_for_date

LOG_OVERLAP_DAYS = 3
MATCHUP_DAYS = 3
PLAYOFF_MONTHS = (4, 5, 6)


def to_raw_matchups(rows: list[dict], game: dict) -> list[dict]:
    raw = []
    for r in rows:
        off_team = r.get("off_team") or ""
        def_team = game["away_team"] if off_team == game["home_team"] else game["home_team"]
        raw.append({**r, "def_team": def_team, "series_id": game.get("series_id")})
    return raw


def _refresh_rosters(repo, nba, teams, warnings) -> None:
    before = {p["id"]: p for p in repo.load_players()}
    seen: set[int] = set()
    ok = 0
    for t in teams:
        try:
            rows = nba.roster(t["id"], t["abbreviation"])
        except Exception as exc:
            warnings.append(f"effectif {t['abbreviation']} : {type(exc).__name__}")
            continue
        ok += 1
        if rows:
            repo.upsert_players(rows)
            seen |= {r["id"] for r in rows}
    if teams and ok == len(teams):
        repo.set_inactive(pid for pid, p in before.items() if p.get("active", True) and pid not in seen)


def _load_logs(repo, nba, season, season_type, date_from, warnings) -> None:
    try:
        games, logs, players = nba.league_game_log(season, season_type, date_from)
    except Exception as exc:
        warnings.append(f"LeagueGameLog {season} {season_type} : {type(exc).__name__}")
        return
    if not logs:
        return
    known = {p["id"] for p in repo.load_players()}
    missing = [{"id": p["id"], "name": p["name"], "team": p["team"], "position": "F", "active": False}
               for pid, p in players.items() if pid not in known]
    if missing:
        repo.upsert_players(missing)
    repo.upsert_games(list(games.values()))
    repo.upsert_game_logs(logs)


def _load_matchups(repo, nba, today, warnings) -> None:
    finals = [g for g in repo.load_games_between(today - timedelta(days=MATCHUP_DAYS), today - timedelta(days=1))
              if is_eligible(g.get("game_type", "unknown")) and g.get("status") == "final"]
    done = repo.game_ids_with_matchups(g["id"] for g in finals)
    for g in finals:
        if g["id"] in done:
            continue
        try:
            rows = nba.matchups(g["id"])
        except Exception as exc:
            warnings.append(f"matchups {g['id']} : {type(exc).__name__}")
            continue
        if rows:
            repo.upsert_matchups_raw(to_raw_matchups(rows, g))


def run(repo, nba, today: date, teams: list[dict], backfill_season: str | None = None) -> list[str]:
    warnings: list[str] = []
    _refresh_rosters(repo, nba, teams, warnings)
    if backfill_season:
        for season_type in ("Regular Season", "Playoffs"):
            _load_logs(repo, nba, backfill_season, season_type, None, warnings)
    else:
        season = season_for_date(today)
        start = today - timedelta(days=LOG_OVERLAP_DAYS)
        _load_logs(repo, nba, season, "Regular Season", start, warnings)
        if today.month in PLAYOFF_MONTHS:
            _load_logs(repo, nba, season, "Playoffs", start, warnings)
    _load_matchups(repo, nba, today, warnings)
    return warnings


def main() -> None:
    from nba_api.stats.static import teams as nba_teams

    from engine.io.guard import ApiGuard
    from engine.io.nba import NbaSource
    from engine.io.repo import SupabaseRepo

    parser = argparse.ArgumentParser(description="Job local (stats.nba.com)")
    parser.add_argument("--backfill-season", help="charge une saison complète, ex. 2025-26")
    args = parser.parse_args()

    guard = ApiGuard()
    repo = SupabaseRepo.from_env()
    today = datetime.now(UTC).astimezone(PARIS).date()
    log_id = repo.start_log("local_nightly")
    try:
        warnings = run(repo, NbaSource(guard, allow_stats=True), today, nba_teams.get_teams(),
                       backfill_season=args.backfill_season)
    except Exception as exc:
        repo.finish_log(log_id, status="error", error=str(exc), api_calls=guard.summary())
        raise
    repo.finish_log(log_id, status="success", api_calls=guard.summary(),
                    error="; ".join(warnings) if warnings else None)
    print(f"local_nightly {today} : {len(warnings)} avertissement(s)")
    for w in warnings:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Relancer le test**

Run: `./venv/bin/python -m pytest tests/jobs -v`
Expected: PASS (4 + 5 tests)

- [ ] **Step 5: Commiter**

```bash
git add engine/jobs/local_nightly.py tests/jobs
git commit -m "feat(jobs): local_nightly (effectifs, LeagueGameLog, matchups bruts)"
```

---

### Task 15: Bascule : workflows, dépendances, suppression de `sync/`, docs

**Files:**
- Modify: `.github/workflows/daily-sync.yml`, `.github/workflows/ci.yml`, `requirements.txt`, `requirements-dev.txt`, `README.md`, `docs/operations.md`, `docs/strategie-ttfl.md`, `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md`
- Delete: `sync/`, `tests/test_advisor.py`, `tests/test_fetcher.py`, `tests/test_personal_strategy.py`, `tests/test_scoring.py`, `tests/test_strategy.py`, `tests/test_ttfl.py`

**Interfaces:**
- Consumes: `engine.jobs.daily_sync.main`, `engine.jobs.local_nightly.main`.
- Produces: dépôt sans `sync/` ; CI et workflow sur `engine`.

- [ ] **Step 1: Vérifier qu'aucun code conservé n'importe `sync`**

Run: `grep -rn "sync\." --include=*.py engine tests | grep -v "daily_sync\|engine/jobs" ; grep -rln "from sync\|import sync" engine tests`
Expected: seuls les 6 tests hérités listés ci-dessus importent `sync`.

- [ ] **Step 2: Supprimer `sync/` et les tests hérités**

```bash
git rm -r -q sync tests/test_advisor.py tests/test_fetcher.py tests/test_personal_strategy.py tests/test_scoring.py tests/test_strategy.py tests/test_ttfl.py
```

- [ ] **Step 3: Épingler les dépendances**

Versions relevées dans le venv de référence (Python 3.14.4) le 2026-09-26.

`requirements.txt` :

```
nba_api==1.11.4
httpx==0.28.1
supabase==2.30.0
numpy==2.4.6
python-dotenv==1.2.2
scipy==1.17.1
```

`requirements-dev.txt` :

```
-r requirements.txt
pytest==9.0.3
psycopg[binary]==3.3.6
```

Plus de `schedule` (inutilisé), et `pytest` n'est plus une dépendance de prod.

- [ ] **Step 4: Mettre le workflow quotidien sur le moteur**

Dans `.github/workflows/daily-sync.yml` :
- supprimer le bloc `inputs:` de `workflow_dispatch` (garder `workflow_dispatch:` seul) ;
- passer `python-version` à `"3.14"` ;
- remplacer l'étape « Run sync » par :

```yaml
      - name: Run sync
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          PYTHONUNBUFFERED: "1"
        run: python -u -m engine.jobs.daily_sync
```

Garder à l'identique le reste (cron 4×/jour, concurrency, étape d'alerte par issue).

Dans `.github/workflows/ci.yml`, retirer les trois variables `SUPABASE_*` et leur commentaire. `engine` ne lit plus l'environnement à l'import. Garder `TEST_DATABASE_URL`.

- [ ] **Step 5: Mettre à jour la documentation**

- `README.md` :
  - remplacer l'affirmation sur le cooldown par « cooldown de 30 jours (J+30) appliqué par le moteur et vérifié en base (trigger `picks_validate`) » ;
  - remplacer toute mention de `sync.main` par `engine.jobs.daily_sync` (GitHub) et `engine.jobs.local_nightly` (cron local).
- `docs/operations.md` :
  - remplacer les commandes `python -m sync.main` par `python -m engine.jobs.daily_sync` / `python -m engine.jobs.local_nightly` ;
  - remplacer la ligne de crontab documentée par :

```
50 23 * * * cd /home/isow/workspace/perso/nba-fantasy && ./venv/bin/python -m engine.jobs.local_nightly >> /tmp/ttfl-local.log 2>&1 || { echo "$(date '+\%F \%T') TTFL local KO" >> /home/isow/ttfl-sync-failures.log; DISPLAY=:0 notify-send -u critical "TTFL local KO" 2>/dev/null; }
```

  - ajouter : « Chargement d'une saison complète (une fois) : `./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26` ».
- `docs/strategie-ttfl.md`, section S2 : remplacer « horizon glissant de 31 jours » par « horizon glissant de 30 jours (J à J+29 : une fenêtre de cooldown J+30) ».
- Spec, §2 (`regular.py`) : même remplacement « 31 j » → « 30 j », et à la ligne « Solveur », remplacer par : « L1 : `linear_sum_assignment` (horizon = une fenêtre de cooldown). `milp` en L2 pour le x2 mensuel. »

- [ ] **Step 6: Lancer la suite complète sans variables Supabase**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest -q`
Expected: PASS (plus aucun test ne dépend de `SUPABASE_*`)

Run: `./venv/bin/python -c "import engine.jobs.daily_sync, engine.jobs.local_nightly; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commiter**

```bash
git add -A .github requirements.txt requirements-dev.txt README.md docs engine tests
git commit -m "refactor: bascule sur engine/, suppression de sync/, dépendances épinglées"
```

---

### Task 16: Réactivation : checklist et chargement de l'historique (avec le feu vert de l'utilisateur)

**Files:**
- Create: `docs/reactivation-saison.md`

**Interfaces:**
- Consumes: `engine.jobs.local_nightly` (`--backfill-season`), `engine.jobs.daily_sync`.
- Produces: checklist versionnée ; historique 2025-26 complet en prod (après feu vert).

- [ ] **Step 1: Écrire la checklist**

`docs/reactivation-saison.md` :

````markdown
# Réactivation des syncs — début de saison

À dérouler dans l'ordre. Les étapes marquées **(prod)** écrivent dans Supabase.

## Une fois, dès que L1b est mergé

1. **(prod)** Historique complet 2025-26 (priors S6 + backtest L2), depuis le PC :
   `./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26`
   Vérifier : `select season, count(*) from game_logs group by 1` (≈ 26 000 lignes pour 2025-26).
2. **(prod)** Effectifs 2026-27 à jour : `./venv/bin/python -m engine.jobs.local_nightly`
   Vérifier : `select count(*) from players where active` (≈ 450-530).

## Quand le calendrier 2026-27 est publié

3. **(prod)** Un passage de `daily_sync` depuis le PC : `./venv/bin/python -m engine.jobs.daily_sync`
   Vérifier :
   - `select game_type, count(*) from games where season='2026-27' group by 1` : la présaison est en `preseason`, et la **finale NBA Cup en `cup_final`** (préfixe `006`). Sinon : migration de correction du préfixe (voir le plan L1a, tâche 9, step 6).
   - `select * from nights order by date limit 5` : aucune soirée de présaison.

## Quelques jours avant le premier match (après L1c)

4. Activer le workflow : `gh workflow enable daily-sync.yml`.
5. Décommenter la ligne de crontab `engine.jobs.local_nightly` (commande dans `docs/operations.md`).
6. Après le passage à l'heure d'hiver (25/10), vérifier les heures du cron GitHub (commentaire dans `daily-sync.yml`).
````

- [ ] **Step 2: Commiter la checklist**

```bash
git add docs/reactivation-saison.md
git commit -m "docs: checklist de réactivation des syncs"
```

- [ ] **Step 3: Demander le feu vert pour les étapes 1-2 (prod)**

Présenter à l'utilisateur les étapes 1 et 2, qui écrivent en prod des joueurs, des matchs et des logs (historique seulement : aucune recommandation, aucun pick modifié). **Attendre un « oui » explicite.**

- [ ] **Step 4: Exécuter les étapes 1 et 2 et vérifier**

Run: `./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26`
Expected: `local_nightly … : N avertissement(s)` sans exception ; la requête de vérification renvoie environ 26 000 lignes 2025-26.

Run: `./venv/bin/python -m engine.jobs.local_nightly`
Expected: 30 effectifs chargés (aucun avertissement « effectif »).

L'étape 3 attend la publication du calendrier 2026-27. Les étapes 4-6 attendent L1c.
