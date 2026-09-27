# L2b — backtest SR, activation du plan, x2 dans le plan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Avant le 1er novembre (premier mois de x2) : le planificateur choisit aussi la soirée du x2 de chaque mois (S3), un backtest rejoue 2025-26 soir par soir pour comparer « meilleur choix du soir », « plan 30 j » et les vrais picks de l'utilisateur, et un drapeau permet d'activer le plan pour la reco du soir si le backtest le justifie.

**Architecture:** Le calcul des entrées du moteur est extrait de `daily_sync.run` dans une fonction pure `build_decision_inputs(...)` que le job quotidien et le backtest partagent. `planner.solve` passe de `linear_sum_assignment` à `scipy.optimize.milp` (HiGHS) pour choisir en même temps l'affectation joueurs/soirées et la soirée x2 de chaque mois. Le backtest (`engine/backtest/`) charge la saison une fois depuis la base (lecture seule), puis pour chaque soirée D ne donne au moteur que ce qui était connu avant D, simule les picks d'une stratégie (cooldown compris) et les note avec les vrais scores.

**Tech Stack:** Python 3.14 (scipy 1.17 `milp`, numpy, pytest), Postgres (Supabase), Next.js 16 (Node 22, vitest).

**Spec:** `docs/superpowers/specs/2026-09-27-l2-design.md` §4 (L2b) ; spec de base `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md` §2.1 (solveur `milp` en L2), §2.2, §7 (backtest, règle d'activation) ; stratégie `docs/strategie-ttfl.md` S1, S2, S3 ; règles `docs/regles-ttfl.md` (R3 cooldown J+30, R7 DNP = 0, R10 x2, R14 moyenne).

## Global Constraints

- **Le backtest ne fait aucun appel externe** et ne lit la base qu'en lecture (spec §7). Aucune écriture en prod hors de la tâche 10 (feu vert de l'utilisateur).
- **Pas de fuite du futur** : pour la soirée D, le moteur ne voit que les `game_logs` de date < D, l'équipe du joueur telle que connue avant D, et le calendrier (connu d'avance). Le score d'une soirée ne sert qu'à la noter.
- **R10 x2** : 1 par mois de novembre à avril (mois de la date US), saison régulière seulement ; double le score, négatif compris ; perdu (0) si le joueur ne joue pas. Fin de mois : si le x2 du mois n'est pas posé et que la dernière soirée éligible du mois est dans l'horizon, il est forcé sur la meilleure option restante (S3).
- **R14** : moyenne sur toutes les soirées éligibles ; soirée sans pick = 0 ; DNP = 0 (R7).
- **Règle d'activation (spec §7)** : le plan ne pilote la reco du soir que s'il bat le meilleur choix du soir au backtest ; l'utilisateur voit les chiffres avant ; l'activation est un drapeau de configuration, par défaut `best_available`.
- Front : Node 22 (`export PATH=/home/isow/.nvm/versions/node/v22.23.3/bin:$PATH`), lire `web/node_modules/next/dist/docs/` avant du code Next. Python : `./venv/bin/python -m pytest -q` ; SQL : `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres`.
- Le `.env` racine et `web/.env.local` pointent la prod : ne jamais lancer `daily_sync`/`local_nightly`, ni `npm run dev` avec des clics d'écriture. Le backtest (lecture seule) peut tourner contre la prod à la tâche 10.
- Commits en français, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Équipe du joueur au moment D** : la table `players` contient les effectifs 2026-27 ; un joueur transféré depuis doit être rattaché à son équipe *d'alors* (dernier `game_logs.team` avant D), sinon le backtest pick des joueurs qui ne jouaient pas ce soir-là. Test tâche 6.
2. **Mois de x2 à cheval sur l'horizon** : un mois dont la fin dépasse l'horizon ne doit pas forcer le x2 ; un mois déjà servi (pick `is_x2` existant ce mois-là) n'en reçoit pas d'autre ; octobre et les playoffs n'en ont jamais. Tests tâche 3.
3. **Blessures inconnues dans le passé** : aucune historique des statuts ; le backtest tourne en deux modes (sans information / « oracle » des DNP) et les compare, au lieu de conclure sur un seul. Test tâche 6.
4. **Égalité MILP ↔ affectation** : sans mois de x2 dans l'horizon, le nouveau solveur doit donner la même valeur totale que l'ancien `linear_sum_assignment` (non-régression du plan actuel). Test tâche 3.
5. **Soirée où le joueur choisi ne joue pas** (DNP, pas de log) : 0 point, x2 perdu, cooldown quand même consommé (R7). Test tâche 6.

---

### Task 1: Migration 026 — `period_stats` borné et limité aux soirées éligibles

**Files:**
- Create: `supabase/migrations/026_period_stats_bounds.sql`, `tests/sql/test_026_period_stats.py`

**Interfaces:**
- Produces: `period_stats(p_season, p_mode, p_until)` avec la même signature et les mêmes colonnes ; `picks`, `zeros` et `x2_used` ne comptent que les picks de soirées éligibles (`nights` non fantômes, `n_eligible_games > 0`) de date < `p_until`.

- [ ] **Step 1: Tests** — `tests/sql/test_026_period_stats.py` : une saison fictive avec 3 soirées éligibles (dont une sans pick), un pick x2 le 2026-11-05, un pick x2 **futur** le 2026-11-20 (réservé), un pick à 0, et un pick sur une date sans ligne `nights` (non éligible). Attendus pour `period_stats('2026-27','regular','2026-11-10')` : `x2_used = 1` (le réservé du 20/11 n'est pas compté), `picks` et `zeros` excluent le pick hors `nights`. Ajouter aussi les cas manquants signalés en L1c : `player_calendar(...)` renvoie `ok = true` pour un joueur libre ; `picks_x2_window` refuse un x2 en mai et en mode playoffs.
- [ ] **Step 2: Échec** — Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql/test_026_period_stats.py -q` → FAIL.
- [ ] **Step 3: Migration** — `create or replace function period_stats(...)` : reprendre le corps de 021 ; remplacer les trois sous-requêtes `picks`/`zeros`/`x2_used` par des jointures sur le CTE `n` (soirées éligibles < `p_until`) :

```sql
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode)::int,
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
            where p.actual_score = 0)::int,
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
            where p.is_x2)::int
```
- [ ] **Step 4: Suite SQL** — Run: `TEST_DATABASE_URL=... ./venv/bin/python -m pytest tests/sql -q` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "fix(db): period_stats borné à p_until et aux soirées éligibles (026)"`.

---

### Task 2: Extraire `build_decision_inputs` de `daily_sync`

**Files:**
- Create: `engine/strategy/inputs.py`, `tests/strategy/test_inputs.py`
- Modify: `engine/jobs/daily_sync.py`

**Interfaces:**
- Produces:

```python
def build_decision_inputs(
    *, today: date, players: dict[int, dict], games: list[dict], logs: list[GameLog],
    season: str, prior: str, picks: list[PickRow], second_chances: list[SecondChance],
    series_rows: list[dict], nights: list[Night],
) -> tuple[DecisionInputs, dict[int, PlayerProfile]]:
    """Profils (S6, role_scales), défense, recent_logs, lignes de séries :
    tout ce que daily_sync calculait entre le chargement des données et
    decide(). Pure : aucune I/O. `logs` = logs des saisons season et prior."""
```

  `daily_sync.run` l'appelle au lieu de son code inline (comportement identique) ; le backtest l'appellera avec des données tronquées à D.
- **Ne pas** retirer les méthodes cdn.nba.com de `engine/io/nba.py` : l'utilisateur veut retester cette API au début de la saison (`docs/reactivation-saison.md`).

- [ ] **Step 1: Test** — `tests/strategy/test_inputs.py` : avec deux joueurs, des logs courants et antérieurs, vérifier que `build_decision_inputs` renvoie les mêmes profils que `build_profile(...)` appelé à la main, `recent_logs[pid]` = minutes des 5 derniers logs du plus récent au plus ancien, et que les joueurs `active: False` n'ont pas de profil.
- [ ] **Step 2: Échec** — `./venv/bin/python -m pytest tests/strategy/test_inputs.py -q` → FAIL.
- [ ] **Step 3: Implémenter** — déplacer le code de `daily_sync.run` (de `rosters = defaultdict(list)` jusqu'à la construction de `DecisionInputs`, sans les écritures en base) dans `inputs.py` ; `run` garde le chargement, `player_aggregates`/`upsert_players`, `replace_nights`, les écritures de recos et de plan.
- [ ] **Step 4: Non-régression** — `./venv/bin/python -m pytest -q` → toute la suite PASS, tests de `daily_sync` inchangés.
- [ ] **Step 5: Commit** — `git commit -m "refactor(engine): entrées du moteur extraites de daily_sync (partagées avec le backtest)"`.

---

### Task 3: Planificateur MILP avec le x2 mensuel (S3)

**Files:**
- Modify: `engine/strategy/planner.py`, `engine/strategy/regular.py`, `engine/strategy/value.py`, `tests/strategy/test_planner.py`, `tests/strategy/test_regular.py`, `engine/jobs/daily_sync.py`

**Interfaces:**
- Consumes: `Cell` (planner), `decide`.
- Produces:
  - `Cell` gagne `x2_gain: float = 0.0` (gain attendu si ce pick est doublé) ;
  - `X2_MONTHS = frozenset({11, 12, 1, 2, 3, 4})` et `X2_RISK_K = 0.5` dans `engine/strategy/value.py`, avec `def x2_gain(p_play: float, projection: float, stddev: float) -> float: return p_play * (projection - X2_RISK_K * stddev)` (S3 : valeur doublée pénalisée par le risque ; un DNP perd le x2) ;
  - `@dataclass(frozen=True) class PlanEntry: cell: Cell; is_x2: bool` et `solve(cells, nights, required=frozenset(), x2_months: dict[tuple[int, int], bool] | None = None) -> dict[date, PlanEntry]` où `x2_months[(année, mois)] = forcé` liste les mois où un x2 est encore disponible (absents = pas de x2 possible), `forcé = True` si la dernière soirée éligible du mois est dans l'horizon ;
  - `Decision.plan: dict[date, PlanEntry]` ; `DecisionInputs` gagne `x2_used_months: frozenset[tuple[int, int]] = frozenset()` (mois où un pick `is_x2` existe déjà) ;
  - `daily_sync` écrit `is_x2` depuis `PlanEntry.is_x2` dans `plan`.

- [ ] **Step 1: Tests du solveur** — dans `tests/strategy/test_planner.py` (adapter les tests existants à `PlanEntry` : `plan[d].cell` au lieu de `plan[d]`) et ajouter :

```python
def test_milp_egal_affectation_sans_x2():
    # 3 joueurs, 3 soirées, valeurs choisies pour que le glouton se trompe
    cells = [_cell(1, D1, 10), _cell(1, D2, 9), _cell(2, D1, 9), _cell(2, D2, 1), _cell(3, D3, 5)]
    plan = solve(cells, [D1, D2, D3])
    assert sum(e.cell.value for e in plan.values()) == 23          # optimum : 2→D1, 1→D2, 3→D3
    assert not any(e.is_x2 for e in plan.values())


def test_x2_sur_le_meilleur_gain_du_mois():
    cells = [_cell(1, D1, 30, x2=20), _cell(2, D2, 30, x2=35)]   # même valeur, gain x2 différent
    plan = solve(cells, [D1, D2], x2_months={(D1.year, D1.month): False})
    assert [d for d, e in plan.items() if e.is_x2] == [D2]


def test_x2_non_force_si_gain_negatif():
    cells = [_cell(1, D1, 10, x2=-5)]
    assert not solve(cells, [D1], x2_months={(D1.year, D1.month): False})[D1].is_x2


def test_x2_force_en_fin_de_mois():
    cells = [_cell(1, D1, 10, x2=-5)]
    assert solve(cells, [D1], x2_months={(D1.year, D1.month): True})[D1].is_x2


def test_pas_de_x2_hors_mois_listes():
    cells = [_cell(1, D1, 10, x2=50)]
    assert not solve(cells, [D1], x2_months={})[D1].is_x2


def test_un_seul_x2_par_mois_et_un_par_mois_distinct():
    cells = [_cell(1, D1, 30, x2=20), _cell(2, D2, 30, x2=25), _cell(3, D4, 30, x2=10)]
    months = {(D1.year, D1.month): False, (D4.year, D4.month): False}
    plan = solve(cells, [D1, D2, D4], x2_months=months)
    assert [d for d, e in plan.items() if e.is_x2] == [D2, D4]
```

(`_cell(pid, night, value, x2=0.0)` construit `Cell(pid, night, value, 1.0, value, CTX, x2_gain=x2)` ; `D1 = date(2026, 11, 3)`, `D2 = date(2026, 11, 10)`, `D3 = date(2026, 11, 17)`, `D4 = date(2026, 12, 2)`.)

- [ ] **Step 2: Échec** — `./venv/bin/python -m pytest tests/strategy/test_planner.py -q` → FAIL.
- [ ] **Step 3: Implémenter le solveur**

```python
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass(frozen=True)
class PlanEntry:
    cell: Cell
    is_x2: bool


def _kept_cells(cells: list[Cell], nights: list[date]) -> list[Cell]:
    wanted = set(nights)
    best: dict[tuple[int, date], Cell] = {}
    for c in cells:
        if c.night in wanted and ((c.player_id, c.night) not in best or c.value > best[(c.player_id, c.night)].value):
            best[(c.player_id, c.night)] = c
    by_night: dict[date, list[Cell]] = defaultdict(list)
    for c in best.values():
        by_night[c.night].append(c)
    return [c for night_cells in by_night.values()
            for c in sorted(night_cells, key=lambda c: c.value, reverse=True)[:TOP_PER_NIGHT]]


def solve(cells, nights, required=frozenset(), x2_months=None) -> dict[date, PlanEntry]:
    """Affectation joueurs × soirées (chaque joueur au plus une fois = R3 sur
    30 j, chaque soirée au plus un joueur) et soirée x2 de chaque mois (S3),
    résolues ensemble par programmation linéaire en nombres entiers (HiGHS).
    Variables : x[i] = cellule i retenue, z[i] = cellule i retenue ET doublée."""
    x2_months = x2_months or {}
    kept = _kept_cells(cells, nights)
    if not kept:
        return {}
    n = len(kept)
    month_of = [(c.night.year, c.night.month) for c in kept]
    obj = np.zeros(2 * n)
    ub = np.ones(2 * n)
    for i, c in enumerate(kept):
        obj[i] = -(c.value + (_REQUIRED_BONUS if c.night in required else 0.0))
        if month_of[i] in x2_months:
            obj[n + i] = -c.x2_gain
        else:
            ub[n + i] = 0.0
    rows, lo, hi = [], [], []

    def add(coefs: dict[int, float], low: float, high: float) -> None:
        r = np.zeros(2 * n)
        for j, v in coefs.items():
            r[j] = v
        rows.append(r); lo.append(low); hi.append(high)

    for key in {c.player_id for c in kept}:
        add({i: 1.0 for i, c in enumerate(kept) if c.player_id == key}, 0, 1)
    for night in {c.night for c in kept}:
        add({i: 1.0 for i, c in enumerate(kept) if c.night == night}, 0, 1)
    for i in range(n):
        add({n + i: 1.0, i: -1.0}, -np.inf, 0)                      # z_i ≤ x_i
    for month, forced in x2_months.items():
        idx = [i for i in range(n) if month_of[i] == month]
        if idx:
            add({n + i: 1.0 for i in idx}, 1 if forced else 0, 1)
    res = milp(c=obj, constraints=LinearConstraint(np.array(rows), lo, hi),
               integrality=np.ones(2 * n), bounds=Bounds(np.zeros(2 * n), ub))
    if res.status != 0 or res.x is None:
        raise RuntimeError(f"planificateur : pas de solution ({res.message})")
    plan = {kept[i].night: PlanEntry(kept[i], bool(res.x[n + i] > 0.5)) for i in range(n) if res.x[i] > 0.5}
    return dict(sorted(plan.items()))
```

Note : un mois « forcé » dont toutes les cellules sont hors plan (soirée non retenue) rend le problème infaisable → ne forcer que si au moins une cellule du mois existe **et** que la soirée correspondante est requise ou remplissable ; en pratique `decide` ne force que si la dernière soirée du mois est dans l'horizon. Si `milp` échoue avec des mois forcés, relancer une fois sans forcer (journaliser). Supprimer `linear_sum_assignment` et `_SENTINEL`.

- [ ] **Step 4: `decide`** — dans `regular.py` : calculer `x2_gain(p, projection, profile.stddev)` pour chaque cellule du planificateur (et 0 pour les soirées en mode playoffs) ; construire `x2_months` : pour chaque (année, mois) des soirées de l'horizon avec `mois ∈ X2_MONTHS`, en mode `regular`, absent de `inputs.x2_used_months` ; `forcé = True` si la dernière soirée éligible (non fantôme) de ce mois dans `inputs.nights` est ≤ dernière soirée de l'horizon ; passer à `solve`. Les soirées déjà réservées (`fixed`) restent hors du plan ; si une réservation porte déjà `is_x2`, son mois est dans `x2_used_months` (le job le calcule depuis les picks). Tests dans `tests/strategy/test_regular.py` : un mois déjà servi n'a pas de x2 ; octobre n'en a pas ; un mois entièrement visible force son x2.
- [ ] **Step 5: `daily_sync`** — `x2_used_months = {(p.date.year, p.date.month) for p in picks if p.is_x2 and p.mode == "regular"}` (ajouter `is_x2` à `PickRow` ou le lire à côté) ; lignes `plan` : `"is_x2": entry.is_x2`, `entry.cell` pour le reste. Test : un plan avec x2 écrit `is_x2: True` sur la bonne soirée.
- [ ] **Step 6: Suite** — `./venv/bin/python -m pytest -q` → PASS.
- [ ] **Step 7: Commit** — `git commit -m "feat(engine): planificateur MILP avec la soirée x2 du mois (S3)"`.

---

### Task 4: Drapeau d'activation du plan pour la reco du soir

**Files:**
- Create: `engine/strategy/config.py`
- Modify: `engine/strategy/regular.py`, `tests/strategy/test_regular.py`

**Interfaces:**
- Produces: `TONIGHT_SOURCE: Literal["best_available", "plan"] = "best_available"` dans `engine/strategy/config.py` (commentaire : « Règle d'activation spec §7 : passer à "plan" seulement si le backtest L2b le justifie et que l'utilisateur l'a validé ») ; `decide(inputs, tonight_source: str = TONIGHT_SOURCE)` : avec `"plan"`, si `plan[today]` existe, sa cellule (valeur S1 recalculée comme les autres recos) est placée en rang 1 des recommandations, le reste gardant l'ordre par valeur ; avec `"best_available"`, comportement actuel inchangé.

- [ ] **Step 1: Tests** — un cas où le meilleur choix du soir (valeur S1 max) diffère de `plan[today]` : `tonight_source="best_available"` → rang 1 = meilleur choix ; `"plan"` → rang 1 = joueur du plan, et il n'apparaît qu'une fois dans la liste.
- [ ] **Step 2: Échec**, **Step 3: Implémenter**, **Step 4: `./venv/bin/python -m pytest -q` → PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(engine): drapeau d'activation du plan pour la reco du soir (défaut : meilleur choix)"`.

---

### Task 5: Données du backtest (chargement unique, vues « connu avant D »)

**Files:**
- Create: `engine/backtest/__init__.py`, `engine/backtest/data.py`, `tests/backtest/__init__.py`, `tests/backtest/test_data.py`
- Modify: `engine/io/repo.py` (méthodes de lecture seulement, si manquantes)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class SeasonData:
    season: str
    prior: str
    players: dict[int, dict]          # id -> {id, name, position} (équipe NON fiable : effectifs actuels)
    games: list[dict]                 # games de la saison (id, date, home_team, away_team, game_type, tip_off, status)
    logs: list[GameLog]               # saison + saison précédente
    picks: list[dict]                 # vrais picks de l'utilisateur (date, player_id, actual_score, is_x2, mode)
    second_chances: list[dict]

def load_season(repo, season: str) -> SeasonData                        # lecture seule, paginée
def logs_before(data: SeasonData, d: date) -> list[GameLog]             # date < d
def team_before(data: SeasonData, player_id: int, d: date) -> str | None
    """Dernière équipe connue avant d (dernier log < d) ; si aucun log avant d
    cette saison, première équipe de la saison ; None si aucun log."""
def roster_before(data: SeasonData, d: date, window_days: int = 30) -> dict[int, dict]
    """Joueurs actifs vus avant d : ayant un log dans la saison courante (ou
    la précédente pour le début de saison), avec `team` = team_before et
    `injury_status` = None."""
def eligible_nights(data: SeasonData, start: date, end: date) -> list[Night]  # build_nights(games, [])
def score_on(data: SeasonData, player_id: int, d: date) -> int         # ttfl_score du log de ce soir, 0 si absent ou 0 min (R7)
def played_on(data: SeasonData, player_id: int, d: date) -> bool       # log avec minutes > 0
```

- [ ] **Step 1: Tests** — données synthétiques : joueur transféré BOS → DAL le 2026-02-10 : `team_before(..., 2026-02-05) == "BOS"`, `team_before(..., 2026-02-15) == "DAL"` ; `logs_before` exclut le jour même ; `score_on` = 0 pour un log à 0 minute et pour l'absence de log ; `roster_before` ne contient pas un joueur dont le seul log est après d ; `eligible_nights` ignore présaison et play-in.
- [ ] **Step 2: Échec**, **Step 3: Implémenter** (réutiliser `GameLog.from_row`, `build_nights`), **Step 4: PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(backtest): chargement de la saison et vues « connu avant D »"`.

---

### Task 6: Simulation soir par soir

**Files:**
- Create: `engine/backtest/simulate.py`, `tests/backtest/test_simulate.py`

**Interfaces:**
- Consumes: `SeasonData` et fonctions de la tâche 5, `build_decision_inputs` (tâche 2), `decide(..., tonight_source)` (tâches 3-4).
- Produces:

```python
@dataclass(frozen=True)
class NightResult:
    night: date
    player_id: int | None
    is_x2: bool
    points: int            # score × 2 si x2 (négatif compris), 0 si pas de pick ou DNP

@dataclass(frozen=True)
class BacktestResult:
    strategy: str          # "best_available" | "plan" | "user"
    injury_mode: str       # "none" | "dnp_oracle"
    nights: list[NightResult]
    @property
    def average(self) -> float        # R14 : somme / nombre de soirées éligibles
    @property
    def zeros(self) -> int            # soirées à 0 point
    @property
    def x2_gain(self) -> int          # points apportés par les x2 (somme des scores doublés - score simple)

def simulate(data: SeasonData, start: date, end: date, strategy: str, injury_mode: str = "none",
             decay: float | None = None) -> BacktestResult
def user_result(data: SeasonData, start: date, end: date) -> BacktestResult   # vrais picks sur la même fenêtre
```

  Boucle de `simulate`, pour chaque soirée éligible D de [start, end] dans l'ordre :
  1. vues « avant D » : `logs_before`, `roster_before` ;
  2. `injury_mode == "dnp_oracle"` : pour D seulement, les joueurs du roster qui avaient joué au moins 1 de leurs 5 derniers matchs et qui n'ont pas joué le soir D reçoivent `injury_status = "Out"` (approximation optimiste des blessures annoncées ; dans le mode `"none"`, personne n'est blessé : approximation pessimiste) ;
  3. picks simulés passés de la stratégie → `PickRow` (cooldown R3 sur l'historique simulé, pas sur celui de l'utilisateur), `x2_used_months` simulés ;
  4. `build_decision_inputs(today=D, ...)` puis `decide(inputs, tonight_source=strategy)` ;
  5. pick du soir = recommandation de rang 1 ; `is_x2` = `plan[D].is_x2` si la cellule de rang 1 est celle du plan, sinon `False` pour `"best_available"` sauf la règle simple de fin de mois : x2 posé sur la dernière soirée éligible du mois si pas encore utilisé (référence naïve pour mesurer le gain du x2 planifié) ;
  6. `points = score_on(...) × (2 si x2)` ; DNP → 0 et x2 perdu (R7, R10) ;
  7. le pick simulé est ajouté à l'historique (même en cas de DNP : le cooldown est consommé).
  `decay` remplace temporairement `value.FUTURE_DECAY` (paramètre explicite passé jusqu'à `lock_value`/`future_value`, pas une variable globale modifiée).

- [ ] **Step 1: Tests** — saison synthétique de 6 soirées et 4 joueurs (fixtures locales) :
  - pas de fuite : le log du soir D n'est jamais dans les entrées de D (espionner `build_decision_inputs` ou vérifier via un joueur dont seul le log de D est énorme → il n'est pas choisi plus haut que sa moyenne passée ne le justifie) ;
  - cooldown : un joueur choisi en D1 n'est pas rechoisi avant D1+30 ;
  - DNP : le joueur choisi ne joue pas → 0 point, compté dans `zeros`, cooldown consommé ;
  - x2 : un x2 sur un score négatif double le négatif ; un x2 sur DNP = 0 ;
  - `average` = somme / nombre de soirées éligibles (soirée sans candidat = 0) ;
  - `user_result` reproduit les points des vrais picks (x2 compris) ;
  - `dnp_oracle` : un joueur qui ne joue pas le soir D n'est jamais choisi ce soir-là.
- [ ] **Step 2: Échec**, **Step 3: Implémenter**, **Step 4: `./venv/bin/python -m pytest tests/backtest -q` → PASS**, puis toute la suite.
- [ ] **Step 5: Commit** — `git commit -m "feat(backtest): simulation soir par soir (meilleur choix, plan, vrais picks)"`.

---

### Task 7: Job `backtest` et rapport

**Files:**
- Create: `engine/jobs/backtest.py`, `tests/jobs/test_backtest_job.py`
- Modify: `docs/operations.md`

**Interfaces:**
- Produces: `python -m engine.jobs.backtest --season 2025-26 --from 2026-02-01 --to 2026-04-12 [--decay 0.97,0.985,1.0] [--out docs/backtest/2025-26-sr.md]` : charge la saison **en lecture seule** (`SupabaseRepo.from_env()`), lance `simulate` pour `best_available` et `plan` dans les deux modes de blessure (et chaque `decay` demandé pour `plan`), plus `user_result` ; écrit un rapport Markdown : tableau par stratégie × mode (moyenne R14, zéros, gain x2, nombre de soirées), écart plan − meilleur choix, et une conclusion factuelle selon la règle d'activation (« le plan bat / ne bat pas le meilleur choix dans les deux modes »). Aucune écriture en base (le job n'appelle aucune méthode d'écriture du repo — le vérifier par test avec un faux repo qui lève sur toute écriture).

- [ ] **Step 1: Test** — avec un faux repo (lecture seule, écritures qui lèvent) et une petite saison synthétique : le job écrit le rapport, contient les 5 lignes attendues (2 stratégies × 2 modes + vrais picks), et n'écrit rien en base.
- [ ] **Step 2: Échec**, **Step 3: Implémenter**, **Step 4: PASS**.
- [ ] **Step 5: Docs** — `docs/operations.md` : section « Backtest » (commande, lecture seule, limites : pas d'historique des blessures → deux modes ; saison 2024-25 absente → fenêtre février-avril 2026 par défaut).
- [ ] **Step 6: Commit** — `git commit -m "feat(jobs): backtest en lecture seule et rapport Markdown"`.

---

### Task 8: Reconstruction des soirées 2025-26

**Files:**
- Create: `engine/jobs/rebuild_nights.py`, `tests/jobs/test_rebuild_nights.py`

**Interfaces:**
- Produces: `python -m engine.jobs.rebuild_nights --season 2025-26` : `build_nights` sur les matchs de la saison, écrit les lignes `nights` **uniquement pour les dates antérieures à aujourd'hui** et **sans supprimer** de ligne existante (upsert sur `date`) ; affiche le nombre de soirées écrites. Sert à `period_stats('2025-26', ...)` (page Picks de la saison passée) ; le backtest n'en dépend pas.

- [ ] **Step 1: Test** — faux repo : saison avec présaison, play-in et soirées SR → seules les SR/Cup sont écrites, aucune date ≥ aujourd'hui, aucune suppression.
- [ ] **Step 2: Échec**, **Step 3: Implémenter**, **Step 4: PASS**.
- [ ] **Step 5: Commit** — `git commit -m "feat(jobs): reconstruction des soirées d'une saison passée"`.

---

### Task 9: Front — suggestion du x2

**Files:**
- Modify: `web/src/app/page.tsx`, `web/src/components/DeckNight.tsx`, `web/src/app/deck/page.tsx`, `web/src/lib/display.ts`, `web/src/lib/display.test.ts`

**Interfaces:**
- Consumes: `plan_latest.is_x2` (colonne existante de `plan`, 019).
- Produces: `x2Hint(input: { planIsX2: boolean; hasPick: boolean; pickIsX2: boolean; x2Allowed: boolean }): "pose" | "deja" | null` — « pose » si le plan suggère le x2 ce soir, que le x2 est autorisé (mois/mode) et pas encore posé sur ce pick.

- [ ] **Step 1: Tests vitest** de `x2Hint` (4 cas : suggestion, déjà posé, mois interdit, pas de suggestion).
- [ ] **Step 2: Implémenter** : sur Ce soir, un encart « Le plan suggère ton x2 ce soir » (au-dessus de la carte de ton pick, ou à côté de la suggestion si pas de pick) ; dans le Deck, un badge « x2 » sur la suggestion du plan quand `is_x2`. Le x2 reste posé par l'utilisateur (bouton existant).
- [ ] **Step 3: Vérifier** — `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → vert.
- [ ] **Step 4: Commit** — `git commit -m "feat(web): suggestion du x2 du plan (Ce soir, Deck)"`.

---

### Task 10: Résultats et mise en prod (feu vert de l'utilisateur à chaque étape)

- [ ] **Step 1: Backtest (lecture seule)** — `./venv/bin/python -m engine.jobs.backtest --season 2025-26 --from 2026-02-01 --to 2026-04-12 --decay 0.97,1.0 --out docs/backtest/2025-26-sr.md` (0.985 = défaut, déjà dans le tableau) ; commit du rapport ; **présenter les chiffres à l'utilisateur**.
- [ ] **Step 2: Décision** — si le plan bat le meilleur choix dans les deux modes de blessure et que l'utilisateur valide : `TONIGHT_SOURCE = "plan"` (et `FUTURE_DECAY` au meilleur `decay`), commit. Sinon, rien ne change et le rapport est consigné dans `docs/strategie-ttfl.md` (S2 : plan indicatif).
- [ ] **Step 3: Migration 026** — `supabase db push --linked --dry-run` ne doit lister que 026 ; puis push.
- [ ] **Step 4: Soirées 2025-26** — `./venv/bin/python -m engine.jobs.rebuild_nights --season 2025-26` (écriture prod) ; vérifier `period_stats('2025-26','regular','2026-06-30')` ≈ 35.0 (moyenne R14 : x2 doublés, soirées sans pick à 0 — cf. ligne « Contexte » du rapport de backtest ; le 34.0 de l'audit est la moyenne brute par pick, sans x2 ni soirées sans pick).
- [ ] **Step 5: Déployer le front** (`cd web && vercel --prod --yes`), merge dans `main`, push, run manuel de `daily-sync.yml` : vérifier qu'un plan avec `is_x2` s'écrit (en novembre) ou que les colonnes restent cohérentes (en octobre, aucun x2).
