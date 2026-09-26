# L1c — Front et authentification : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapter la PWA à la saison régulière. Au programme :
- soirée du deck en heure de Paris, recos avec l'espérance complète (S1), disponibilité « dispo le JJ/MM », réservations à 14 jours, x2, Seconde chance, deck 14 jours, historique avec moyenne sur toutes les soirées ;
- suppression des écrans playoffs ;
- écritures authentifiées (code OTP e-mail) par actions serveur, fin des écritures anonymes.

**Architecture:**
- Aucune règle TTFL n'est réimplémentée en TypeScript. Disponibilité, calendrier d'un joueur, statistiques de période, dernier plan et contraintes x2 sont en SQL (migration 021) ou déjà en base (trigger `picks_validate`, L1a).
- Le front lit avec la clé anon et écrit **uniquement** via des actions serveur. Celles-ci vérifient la session (`requireOwner`) puis écrivent avec la clé service.
- Côté moteur, `local_nightly` charge aussi le calendrier via stats.nba.com, car cdn.nba.com renvoie 403 depuis l'IP locale le 2026-09-26.

**Tech Stack:** Next.js 16.2.3 (App Router, Server Functions, `proxy.ts`), React 19, `@supabase/supabase-js` + `@supabase/ssr`, Tailwind 4, vitest (helpers purs), Postgres (migrations 021-022, tests SQL existants), Python (engine, tâche 1).

**Spec:** `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md` (§3 Sécurité, §6 Front) + `docs/strategie-ttfl.md` (P1, P2) + `docs/regles-ttfl.md`.

**Avant d'écrire du code front :** lire le guide concerné dans `web/node_modules/next/dist/docs/` (cf. `web/AGENTS.md`). En particulier `01-app/01-getting-started/07-mutating-data.md`, `16-proxy.md`, `01-app/02-guides/authentication.md` et `03-api-reference/04-functions/cookies.md`.

## Global Constraints

- **Soirée du deck = date de Paris** (`deckDate()`) pour tout ce qui lit `recommendations`, `nights`, `plan_latest` et `picks` « de ce soir ». `todayNBA()` ne sert plus qu'aux vues de matchs en direct (`/games`). Entre 00:00 et le passage de 07:00, s'il n'y a pas de recos pour la soirée, afficher « Prochaine synchro en cours », jamais les recos de la veille.
- **Aucune règle TTFL en TypeScript.** Disponibilité : `player_calendar` / `player_availability`. Moyenne : `period_stats`. Plan courant : `plan_latest`. Cooldown, éligibilité, x2 : contraintes et trigger en base. Le TS ne fait que formater.
- **Écritures :**
  - uniquement des actions serveur de `web/src/app/actions.ts` (`"use server"`) ;
  - chacune commence par `requireOwner()` (comparaison de l'e-mail de session, en minuscules, avec `OWNER_EMAIL`), puis écrit avec le client service (`import "server-only"`) et appelle `revalidatePath` ;
  - plus aucun `supabase.from(...).insert/update/upsert/delete` côté client.
- **Pick (R2)** : s'il existe déjà un pick à cette date, `UPDATE player_id, game_id` (le trigger revalide). Sinon `INSERT player_id, game_id, date` (mode et saison posés par le trigger). Jamais de suppression puis réinsertion.
- **Réservation (R9)** : date de soirée ≥ `deckDate()` et ≤ `deckDate()` + 14 jours, vérifié dans l'action.
- **Messages d'erreur** : codes Postgres traduits par `pickErrorMessage()`, fonction pure testée. Jamais de message brut à l'écran.
- **Clés** : `SUPABASE_SERVICE_KEY` et `OWNER_EMAIL` sont des variables serveur, jamais `NEXT_PUBLIC_*`, jamais collées dans le chat. `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` restent pour la lecture.
- **Ordre en prod** (tâche 12) : appliquer 021 (ajouts seulement), puis déployer le nouveau front, puis appliquer 022 (suppression des écritures anon). L'ordre inverse empêcherait de picker jusqu'au déploiement.
- **Hors périmètre** : suggestion de x2 (L2), rappels push (L2), écrans PO (L3), filtrage PO des matchs fantômes match par match côté front (L3).
- Commits : message terminé par une ligne vide puis `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Commandes front (depuis `web/`) : `npx tsc --noEmit`, `npm run lint`, `npm test` (vitest), `npm run build`. Tests Python/SQL (depuis la racine) : `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest -q`.

## Prérequis manuels (utilisateur, avant la tâche 12)

1. **Dashboard Supabase → Authentication → Users** : créer l'utilisateur propriétaire avec son e-mail (« Add user », sans mot de passe). Il faut qu'il existe, car les actions de connexion utilisent `shouldCreateUser: false`.
2. **Authentication → Email Templates → « Magic Link »** : remplacer le corps par un message contenant le code `{{ .Token }}` (par ex. « Ton code TTFL Advisor : {{ .Token }} »). Le modèle par défaut n'envoie qu'un lien.
3. Le SMTP intégré de Supabase n'envoie que quelques e-mails par heure : ne pas multiplier les demandes de code pendant les essais.
4. **Vercel → projet `web` → Settings → Environment Variables** (Production) : `SUPABASE_SERVICE_KEY` (clé service Supabase) et `OWNER_EMAIL` (e-mail du propriétaire). Les mêmes dans `web/.env.local` pour le dev local. Ne jamais les coller dans le chat.

## Review Focus

- **Pas encore de recos pour la soirée** (entre minuit et la synchro de 07:00, ou début de saison) : la page affiche « Prochaine synchro en cours », jamais les recos d'hier. Test : tâche 6, `homeState` avec 0 reco.
- **Ligne de reco antérieure à la migration 020** (`p_play`, `value`, `locked_until` à NULL) : aucun plantage, champs masqués. Test : tâche 6, `recMeta` avec des NULL.
- **Pick refusé par le trigger** (cooldown, réservation proche, match inéligible) : message français compréhensible avec la date de retour. Test : tâche 3, `pickErrorMessage`.
- **Action serveur appelée sans session ou avec un autre e-mail** : refus explicite, aucune écriture. Test : tâche 3, `isOwnerEmail` + tâche 5, `requireOwner` appelé en premier (revue).
- **Deux x2 le même mois / x2 hors novembre-avril** : refusé par la base avec un message clair. Test : tâche 2 (SQL) + tâche 3 (mapping 23505/23514).

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `engine/io/nba.py`, `engine/jobs/local_nightly.py`, `tests/jobs/*` | Calendrier via stats.nba.com (ScheduleLeagueV2) |
| `supabase/migrations/021_front_sr.sql` | `plan_latest`, `player_calendar`, `period_stats`, `matchup_season`, contraintes x2 |
| `supabase/migrations/022_lock_anon_writes.sql` | Suppression des policies d'écriture anon (picks, watchlist, forecast) |
| `tests/sql/test_021_front_sr.py`, `tests/sql/test_022_lock_anon_writes.py` | Tests SQL |
| `web/package.json`, `web/vitest.config.ts` | `@supabase/ssr`, `server-only`, vitest |
| `web/src/lib/date.ts` (+ `.test.ts`) | `deckDate`, `addDays`, `seasonForDate`, formatage |
| `web/src/lib/supabase/public.ts`, `server.ts`, `admin.ts` | Clients lecture anon / session / service |
| `web/src/lib/auth.ts` (+ `.test.ts`) | `isOwnerEmail`, `requireOwner` |
| `web/src/lib/errors.ts` (+ `.test.ts`) | `pickErrorMessage` |
| `web/src/lib/display.ts` (+ `.test.ts`) | `recMeta`, `homeState` (formatage NULL-safe) |
| `web/src/proxy.ts` | Rafraîchissement de session Supabase |
| `web/src/app/connexion/*` | Connexion par code e-mail |
| `web/src/app/actions.ts` | `savePick`, `setX2`, `addSecondChance`, `setWatchlist`, `signOut` |
| `web/src/app/page.tsx`, `components/RecommendationCard.tsx`, `PlayerList.tsx`, `MyPickCard.tsx`, `GamesCollapsible.tsx`, `NoPickBanner.tsx` | Écran « Ce soir » |
| `web/src/app/player/[id]/page.tsx`, `PickControls.tsx`, `WatchlistStar.tsx` | Fiche joueur |
| `web/src/app/picks/*` | Historique et statistiques |
| `web/src/app/deck/page.tsx`, `components/DeckNight.tsx` | Deck 14 jours |
| `web/src/types/index.ts`, `components/BottomNav.tsx`, `app/games/page.tsx` | Types, navigation, fenêtre des matchs |
| Supprimés | `app/strategy/*`, `app/series/*`, `components/WatchlistAlerts.tsx`, `StrategyBanner.tsx`, `InjuryArbitrage.tsx`, `app/player/[id]/PickButton.tsx`, `lib/supabase.ts` |
| `.github/workflows/ci.yml` | Job front (lint, tsc, vitest, build) |
| `docs/reactivation-saison.md` | Ordre de mise en prod mis à jour |

---

### Task 1: Calendrier via stats.nba.com dans `local_nightly`

**Files:**
- Modify: `engine/io/nba.py`, `engine/jobs/local_nightly.py`, `tests/jobs/fakes.py`, `tests/jobs/test_local_nightly.py`, `tests/io/test_nba_parsers.py`, `docs/reactivation-saison.md`

**Interfaces:**
- Consumes: `parse_schedule(payload, start, end)` (L1b, même format JSON que le CDN).
- Produces: `NbaSource.schedule_stats(season: str, start: date, end: date) -> list[dict]` (stats.nba.com, `allow_stats` requis) ; `local_nightly.run` charge le calendrier `[today − 5, today + 35]` avant l'historique. Nouvelle constante `SCHEDULE_AHEAD_DAYS = 35`.

- [ ] **Step 1: Écrire les tests**

Dans `tests/io/test_nba_parsers.py`, ajouter :

```python
def test_schedule_stats_interdit_depuis_github():
    src = NbaSource(ApiGuard(), allow_stats=False)
    with pytest.raises(RuntimeError, match="stats.nba.com"):
        src.schedule_stats("2026-27", date(2026, 10, 1), date(2026, 11, 1))
```

Dans `tests/jobs/fakes.py`, ajouter à `FakeStatsSource.__init__` le paramètre `schedule=None` (stocké dans `self._schedule = list(schedule or [])`) et `self.schedule_calls = []`, puis la méthode :

```python
    def schedule_stats(self, season, start, end):
        self.schedule_calls.append((season, start, end))
        return [g for g in self._schedule if start.isoformat() <= g["date"] <= end.isoformat()]
```

Dans `tests/jobs/test_local_nightly.py`, ajouter :

```python
def test_calendrier_charge_via_stats_nba():
    sched = [{"id": "0022600001", "date": "2026-10-20", "home_team": "BOS", "away_team": "NYK", "tip_off": None},
             {"id": "0062600001", "date": "2026-12-11", "home_team": "TBD", "away_team": "TBD", "tip_off": None}]
    repo = FakeRepo()
    nba = FakeStatsSource(schedule=sched)
    run(repo, nba, date(2026, 9, 26), [])
    assert nba.schedule_calls == [("2026-27", date(2026, 9, 21), date(2026, 10, 31))]
    assert repo.games["0022600001"]["game_type"] == "regular"
    assert "0062600001" not in repo.games           # hors fenêtre de 35 jours


def test_calendrier_indisponible_n_arrete_pas_le_job():
    class Boom(FakeStatsSource):
        def schedule_stats(self, season, start, end):
            raise ConnectionError("stats KO")
    warnings = run(FakeRepo(), Boom(), date(2026, 9, 26), [])
    assert any("calendrier" in w for w in warnings)
```

- [ ] **Step 2: Lancer les tests pour constater l'échec**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/io/test_nba_parsers.py tests/jobs/test_local_nightly.py -v`
Expected: FAIL (`AttributeError: 'NbaSource' object has no attribute 'schedule_stats'`, `schedule_calls` vide).

- [ ] **Step 3: Implémenter**

Dans `engine/io/nba.py` : ajouter `ScheduleLeagueV2` à l'import `from nba_api.stats.endpoints import …`, puis ajouter à `NbaSource` :

```python
    def schedule_stats(self, season: str, start: date, end: date) -> list[dict]:
        """Calendrier via stats.nba.com (même JSON que le CDN), pour le cron
        local : cdn.nba.com renvoie 403 depuis l'IP locale (2026-09-26)."""
        self._require_stats()
        payload = self.guard.call(
            "stats.nba.com",
            lambda: ScheduleLeagueV2(league_id="00", season=season, timeout=60).get_dict(),
        )
        return parse_schedule(payload, start, end)
```

Dans `engine/jobs/local_nightly.py` : ajouter `SCHEDULE_PAST_DAYS = 5`, `SCHEDULE_AHEAD_DAYS = 35`, puis la fonction suivante, appelée dans `run()` juste après `_refresh_rosters(...)` et avant l'historique, avec `season_for_date(today)` :

```python
def _load_schedule(repo, nba, season, today, warnings) -> None:
    try:
        rows = nba.schedule_stats(season, today - timedelta(days=SCHEDULE_PAST_DAYS),
                                  today + timedelta(days=SCHEDULE_AHEAD_DAYS))
    except Exception as exc:
        warnings.append(f"calendrier {season} : {type(exc).__name__}")
        return
    if rows:
        repo.upsert_games(rows)
```

Mettre à jour la docstring du module (ajouter « calendrier des 35 prochains jours (stats.nba.com) »).

- [ ] **Step 4: Mettre à jour la checklist**

Dans `docs/reactivation-saison.md`, section « Quand le calendrier 2026-27 est publié » :
- noter que le calendrier est désormais chargé par `local_nightly` (étape 2) ;
- noter que le préfixe `006` de la finale NBA Cup est **vérifié** (`0062600001`, 11/12/2026) ;
- ajouter : « cdn.nba.com renvoie 403 depuis l'IP locale au 2026-09-26 : `daily_sync` s'appuie alors sur le calendrier chargé par le cron local ; les box scores sont rattrapés chaque nuit par LeagueGameLog (scores des picks à J+1 ou J+2). »

- [ ] **Step 5: Relancer la suite complète**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commiter**

```bash
git add engine tests docs/reactivation-saison.md
git commit -m "feat(jobs): calendrier chargé par local_nightly via stats.nba.com"
```

---

### Task 2: Migrations 021 (ajouts) et 022 (fin des écritures anon)

**Files:**
- Create: `supabase/migrations/021_front_sr.sql`, `supabase/migrations/022_lock_anon_writes.sql`, `tests/sql/test_021_front_sr.py`, `tests/sql/test_022_lock_anon_writes.py`

**Interfaces:**
- Produces:
  - vue `plan_latest` (colonnes de `plan`, `security_invoker`) ;
  - `player_calendar(p_player_id int, p_from date, p_to date) -> table(night date, closing_at timestamptz, game_id text, opponent text, is_home boolean, ok boolean, available_from date, reason text)` ;
  - `period_stats(p_season text, p_mode text, p_until date) -> table(nights int, scored_nights int, total int, average numeric, picks int, zeros int, x2_used int)` ;
  - vue `matchup_season(player_id, opponent_team, season, def_player_id, def_player_name, minutes, points, games)` ;
  - index unique `picks_x2_month` et contrainte `picks_x2_window` ;
  - 022 : plus aucune policy insert/update/delete pour anon sur `picks`, `player_watchlist`, `series_forecast`.

- [ ] **Step 1: Écrire les tests**

`tests/sql/test_021_front_sr.py` :

```python
import psycopg
import pytest


def _seed(pg):
    pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G')")
    pg.execute(
        "insert into games (id, date, home_team, away_team) values "
        "('0022600100', '2026-11-01', 'DEN', 'LAL'), ('0022600200', '2026-11-10', 'BOS', 'DEN'), "
        "('0022600300', '2026-11-12', 'PHX', 'LAL')"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "('2026-11-01', '2026-27', 'regular', 1, '2026-11-01T23:00:00Z'), "
        "('2026-11-10', '2026-27', 'regular', 1, '2026-11-10T23:00:00Z'), "
        "('2026-11-12', '2026-27', 'regular', 1, '2026-11-12T23:00:00Z')"
    )


def test_player_calendar_soirees_de_son_equipe_avec_dispo(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600100', '2026-11-01')")
        rows = pg.execute(
            "select night::text, opponent, is_home, ok, available_from::text, reason "
            "from player_calendar(1, '2026-11-01', '2026-11-30')"
        ).fetchall()
        assert rows == [
            ("2026-11-01", "LAL", True, False, "2026-12-01", "cooldown"),
            ("2026-11-10", "BOS", False, False, "2026-12-01", "cooldown"),
        ]   # le 12/11, DEN ne joue pas


def test_period_stats_soir_sans_pick_compte_zero_et_x2_double(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date, actual_score, is_x2) values "
                   "(1, '0022600100', '2026-11-01', 40, true)")
        row = pg.execute("select * from period_stats('2026-27', 'regular', '2026-11-11')").fetchone()
        # soirées 01/11 (80 avec le x2) et 10/11 (sans pick = 0) ; le 12/11 est après la borne
        assert row == (2, 2, 80, 40.0, 1, 0, 1)


def test_period_stats_pick_non_score_exclu(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (2, '0022600100', '2026-11-01')")
        nights, scored, total, average, *_ = pg.execute(
            "select * from period_stats('2026-27', 'regular', '2026-11-02')").fetchone()
        assert (nights, scored, total, average) == (1, 0, 0, None)


def test_plan_latest_ne_garde_que_le_dernier_plan(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into plan (generated_at, night, player_id, projection, p_play, value) values "
            "('2026-10-30T05:00:00Z', '2026-11-01', 1, 50, 1, 50), "
            "('2026-10-31T05:00:00Z', '2026-11-01', 2, 40, 1, 40)"
        )
        assert pg.execute("select player_id from plan_latest").fetchall() == [(2,)]


def test_x2_un_seul_par_mois(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0022600100', '2026-11-01', true)")
        with pytest.raises(psycopg.errors.UniqueViolation, match="picks_x2_month"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (2, '0022600200', '2026-11-10', true)")


def test_x2_interdit_hors_novembre_avril(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into players (id, name, team, position) values (1, 'Jokic', 'DEN', 'C')")
        pg.execute("insert into games (id, date, home_team, away_team) values ('0022600010', '2026-10-25', 'DEN', 'LAL')")
        with pytest.raises(psycopg.errors.CheckViolation, match="picks_x2_window"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date, is_x2) values (1, '0022600010', '2026-10-25', true)")


def test_matchup_season(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into box_score_matchups_raw (game_id, off_player_id, def_player_id, def_team, def_player_name, "
            "matchup_seconds, player_points) values "
            "('0022600100', 1, 99, 'LAL', 'Davis', 600, 12), ('0022600100', 1, 98, 'LAL', 'James', 300, 5)"
        )
        rows = pg.execute(
            "select def_player_name, minutes, points, games from matchup_season "
            "where player_id = 1 and opponent_team = 'LAL' and season = '2026-27' order by minutes desc"
        ).fetchall()
        assert rows == [("Davis", 10, 12, 1), ("James", 5, 5, 1)]
```

`tests/sql/test_022_lock_anon_writes.py` :

```python
def test_plus_aucune_ecriture_anon(pg):
    rows = pg.execute(
        "select tablename, policyname, cmd from pg_policies where schemaname = 'public' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast') and cmd <> 'SELECT'"
    ).fetchall()
    assert rows == []


def test_la_lecture_anon_reste(pg):
    tables = {t for (t,) in pg.execute(
        "select tablename from pg_policies where schemaname = 'public' and cmd = 'SELECT' "
        "and tablename in ('picks', 'player_watchlist', 'series_forecast')").fetchall()}
    assert tables == {"picks", "player_watchlist", "series_forecast"}
```

- [ ] **Step 2: Lancer les tests pour constater l'échec**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql/test_021_front_sr.py tests/sql/test_022_lock_anon_writes.py -v`
Expected: FAIL (`function player_calendar(...) does not exist`, policies anon encore présentes).

- [ ] **Step 3: Écrire la migration 021**

`supabase/migrations/021_front_sr.sql` :

```sql
-- 021 — Lectures du front saison régulière (aucune règle TTFL côté TS) et
-- garde-fous x2 en base (R10). Ajouts uniquement : à appliquer AVANT le
-- déploiement du nouveau front. Idempotente.

-- Dernier plan généré par le moteur (le front ne filtre plus en TS).
create or replace view plan_latest with (security_invoker = true) as
select p.* from plan p
where p.generated_at = (select max(generated_at) from plan);

-- Soirées où l'équipe du joueur joue, avec sa disponibilité (R3/R4/R5/R15).
create or replace function player_calendar(p_player_id int, p_from date, p_to date)
returns table (night date, closing_at timestamptz, game_id text, opponent text,
               is_home boolean, ok boolean, available_from date, reason text)
language sql stable as $$
  select n.date, n.closing_at, g.id,
         case when g.home_team = p.team then g.away_team else g.home_team end,
         g.home_team = p.team, a.ok, a.available_from, a.reason
  from players p
  join nights n on n.date between p_from and p_to
                and not n.is_phantom and n.n_eligible_games > 0
  join games g on g.date = n.date and p.team in (g.home_team, g.away_team)
              and g.game_type in ('regular', 'cup_final', 'playoffs')
  cross join lateral player_available_on(p.id, p.team, n.date, n.season, n.mode, null) a
  where p.id = p_player_id
  order by n.date
$$;

-- Statistiques d'une période (R14 : soirée éligible sans pick = 0 ; pick pas
-- encore scoré = exclu). Miroir de engine.rules.scoring.period_average.
create or replace function period_stats(p_season text, p_mode text, p_until date)
returns table (nights int, scored_nights int, total int, average numeric,
               picks int, zeros int, x2_used int)
language sql stable as $$
  with n as (
    select date from nights
    where season = p_season and mode = p_mode and date < p_until
      and not is_phantom and n_eligible_games > 0
  ), pts as (
    select case
             when p.id is null then 0
             when p.actual_score is null then null
             else p.actual_score * (case when p.is_x2 then 2 else 1 end)
           end as points
    from n left join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
  )
  select (select count(*) from n)::int,
         count(points)::int,
         coalesce(sum(points), 0)::int,
         case when count(points) > 0 then round(avg(points)::numeric, 1) end,
         (select count(*) from picks where season = p_season and mode = p_mode and date < p_until)::int,
         (select count(*) from picks where season = p_season and mode = p_mode and date < p_until and actual_score = 0)::int,
         (select count(*) from picks where season = p_season and mode = p_mode and is_x2)::int
  from pts
$$;

-- Matchups défenseur ↔ attaquant ramenés à la saison (données brutes L1b).
create or replace view matchup_season with (security_invoker = true) as
select r.off_player_id as player_id, r.def_team as opponent_team, g.season,
       r.def_player_id, max(r.def_player_name) as def_player_name,
       round(sum(r.matchup_seconds) / 60.0)::int as minutes,
       sum(r.player_points)::int as points,
       count(distinct r.game_id)::int as games
from box_score_matchups_raw r
join games g on g.id = r.game_id
group by r.off_player_id, r.def_team, g.season, r.def_player_id;

-- R10 : un x2 par mois, en saison régulière, de novembre à avril.
create unique index if not exists picks_x2_month
  on picks (season, (extract(year from date)), (extract(month from date)))
  where is_x2;
alter table picks drop constraint if exists picks_x2_window;
alter table picks add constraint picks_x2_window
  check (not is_x2 or (mode = 'regular' and extract(month from date) in (11, 12, 1, 2, 3, 4)));
```

- [ ] **Step 4: Écrire la migration 022**

`supabase/migrations/022_lock_anon_writes.sql` :

```sql
-- 022 — Fin des écritures anon (spec §3). Les écritures passent par les
-- actions serveur du front (session propriétaire + clé service). À appliquer
-- APRÈS le déploiement du front L1c. La lecture anon est conservée.
-- Idempotente.

drop policy if exists "anon insert picks" on picks;
drop policy if exists "anon delete unscored picks" on picks;
drop policy if exists "anon insert watchlist" on player_watchlist;
drop policy if exists "anon update watchlist" on player_watchlist;
drop policy if exists "anon delete watchlist" on player_watchlist;
drop policy if exists "anon insert forecast" on series_forecast;
drop policy if exists "anon update forecast" on series_forecast;
drop policy if exists "anon delete forecast" on series_forecast;
```

- [ ] **Step 5: Relancer les tests SQL**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -v`
Expected: PASS (dont `test_migrations_rejouables`)

Si `test_player_calendar…` échoue sur l'ordre ou la présence du 12/11, vérifier la jointure `p.team in (g.home_team, g.away_team)` : le 12/11, c'est PHX-LAL, et DEN ne joue pas.

- [ ] **Step 6: Commiter**

```bash
git add supabase/migrations/021_front_sr.sql supabase/migrations/022_lock_anon_writes.sql tests/sql/test_021_front_sr.py tests/sql/test_022_lock_anon_writes.py
git commit -m "feat(db): lectures du front SR, garde-fous x2 (021) et fin des écritures anon (022)"
```

---

### Task 3: Fondations front : dépendances, dates, clients Supabase, auth, erreurs

**Files:**
- Modify: `web/package.json`, `web/src/lib/date.ts`
- Create: `web/vitest.config.ts`, `web/src/lib/date.test.ts`, `web/src/lib/supabase/public.ts`, `web/src/lib/supabase/server.ts`, `web/src/lib/supabase/admin.ts`, `web/src/lib/auth.ts`, `web/src/lib/auth.test.ts`, `web/src/lib/errors.ts`, `web/src/lib/errors.test.ts`
- Delete: `web/src/lib/supabase.ts` (et mise à jour des imports `@/lib/supabase` → `@/lib/supabase/public`)

**Interfaces:**
- Produces:
  - `deckDate(now?: Date): string` (`YYYY-MM-DD`, heure de Paris) ;
  - `addDays(iso: string, n: number): string` ;
  - `seasonForDate(iso: string): string` (`"2026-27"` ; septembre → saison qui commence ; ce n'est pas une règle TTFL) ;
  - `frDayMonth(iso: string): string` (`"24/11"`) ;
  - `frLongDate(iso: string): string` (`"mardi 24 novembre"`) ;
  - `parisTime(isoTimestamp: string): string` (`"23:00"`) ;
  - `supabase` (anon, lecture) depuis `@/lib/supabase/public` ;
  - `createAuthClient(): Promise<SupabaseClient>` (session, cookies) ;
  - `adminClient(): SupabaseClient` (clé service, `server-only`) ;
  - `isOwnerEmail(email: string | null | undefined, owner: string | undefined): boolean` ;
  - `requireOwner(): Promise<string>` (renvoie l'e-mail, lève `Error("non_autorise")` sinon) ;
  - `pickErrorMessage(err: { code?: string; message?: string; details?: string } | null | undefined): string`.

- [ ] **Step 1: Installer les dépendances**

```bash
cd web && npm install @supabase/ssr server-only && npm install -D vitest
```

Ajouter dans `web/package.json` → `"scripts"` : `"test": "vitest run"`.

`web/vitest.config.ts` :

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
```

- [ ] **Step 2: Écrire les tests**

`web/src/lib/date.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { addDays, deckDate, frDayMonth, frLongDate, parisTime, seasonForDate } from "./date";

describe("deckDate", () => {
  it("prend la date de Paris, pas celle de l'heure de l'Est", () => {
    // 2026-11-03 01:30 à Paris = 2026-11-02 19:30 à New York
    expect(deckDate(new Date("2026-11-03T00:30:00Z"))).toBe("2026-11-03");
  });
  it("gère le passage à l'heure d'hiver", () => {
    expect(deckDate(new Date("2026-10-24T22:30:00Z"))).toBe("2026-10-25");
  });
});

describe("helpers", () => {
  it("addDays", () => {
    expect(addDays("2026-11-24", 14)).toBe("2026-12-08");
    expect(addDays("2026-03-28", 1)).toBe("2026-03-29");
  });
  it("seasonForDate", () => {
    expect(seasonForDate("2026-10-20")).toBe("2026-27");
    expect(seasonForDate("2027-04-15")).toBe("2026-27");
    expect(seasonForDate("2026-08-31")).toBe("2025-26");
  });
  it("formats FR", () => {
    expect(frDayMonth("2026-11-24")).toBe("24/11");
    expect(frLongDate("2026-11-24")).toBe("mardi 24 novembre");
    expect(parisTime("2026-11-24T23:00:00Z")).toBe("00:00");
  });
});
```

`web/src/lib/auth.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { isOwnerEmail } from "./auth";

describe("isOwnerEmail", () => {
  it("compare sans tenir compte de la casse", () => {
    expect(isOwnerEmail("Moi@Exemple.fr", "moi@exemple.fr")).toBe(true);
  });
  it("refuse sans session, sans propriétaire configuré ou avec un autre e-mail", () => {
    expect(isOwnerEmail(null, "moi@exemple.fr")).toBe(false);
    expect(isOwnerEmail("moi@exemple.fr", undefined)).toBe(false);
    expect(isOwnerEmail("autre@exemple.fr", "moi@exemple.fr")).toBe(false);
  });
});
```

`web/src/lib/errors.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { pickErrorMessage } from "./errors";

describe("pickErrorMessage", () => {
  it("cooldown avec date de retour", () => {
    expect(pickErrorMessage({ code: "P0001", message: "player_unavailable:cooldown", details: "2026-11-24" }))
      .toBe("Joueur bloqué jusqu'au 24/11 (cooldown de 30 jours).");
  });
  it("réservation proche", () => {
    expect(pickErrorMessage({ code: "P0001", message: "player_unavailable:reserved_nearby" }))
      .toBe("Ce joueur est déjà réservé à moins de 30 jours de cette soirée.");
  });
  it("soirée inéligible", () => {
    expect(pickErrorMessage({ code: "P0001", message: "night_not_eligible:preseason" }))
      .toBe("Cette soirée ne compte pas pour la TTFL (présaison, play-in…).");
  });
  it("x2 déjà utilisé dans le mois", () => {
    expect(pickErrorMessage({ code: "23505", message: 'duplicate key value violates unique constraint "picks_x2_month"' }))
      .toBe("Tu as déjà utilisé ton x2 ce mois-ci.");
  });
  it("x2 hors fenêtre", () => {
    expect(pickErrorMessage({ code: "23514", message: 'new row violates check constraint "picks_x2_window"' }))
      .toBe("Le x2 n'existe qu'en saison régulière, de novembre à avril.");
  });
  it("défaut sans fuite du message brut", () => {
    expect(pickErrorMessage({ code: "XX000", message: "internal" })).toBe("Échec de l'enregistrement — réessaie.");
    expect(pickErrorMessage(null)).toBe("Échec de l'enregistrement — réessaie.");
  });
});
```

- [ ] **Step 3: Lancer les tests pour constater l'échec**

Run: `cd web && npm test`
Expected: FAIL (modules et exports manquants).

- [ ] **Step 4: Implémenter**

`web/src/lib/date.ts` (remplace le fichier ; `todayNBA` et `todayParis` sont conservés) :

```ts
/** Journée NBA (heure de l'Est) : uniquement pour les vues de matchs en direct. */
export function todayNBA(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

/** Aujourd'hui à Paris. */
export function todayParis(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}

/**
 * Soirée du deck TTFL : le deck du jour D ferme à 00:00 heure de Paris (R8).
 * À toute heure de la journée D à Paris, la soirée à préparer est D.
 */
export function deckDate(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Saison NBA d'une date (à partir de septembre, la saison qui commence). */
export function seasonForDate(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  const start = m >= 9 ? y : y - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

export function frDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export function frLongDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  });
}

export function parisTime(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleTimeString("fr-FR", {
    hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris",
  });
}
```

`web/src/lib/supabase/public.ts` (déplacement de `lib/supabase.ts`) :

```ts
import { createClient } from "@supabase/supabase-js";

/** Client anon, lecture seule (les écritures passent par app/actions.ts). */
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);
```

Puis `git rm web/src/lib/supabase.ts` et remplacer partout `from "@/lib/supabase"` par `from "@/lib/supabase/public"` (`grep -rl '@/lib/supabase"' web/src`).

`web/src/lib/supabase/server.ts` :

```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/** Client lié à la session de l'utilisateur (cookies). */
export async function createAuthClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            // Appelé depuis un Server Component (cookies en lecture seule) :
            // le rafraîchissement de session est fait par proxy.ts.
          }
        },
      },
    },
  );
}
```

`web/src/lib/supabase/admin.ts` :

```ts
import "server-only";
import { createClient } from "@supabase/supabase-js";

/** Client service (contourne la RLS) : UNIQUEMENT dans les actions serveur,
 *  après requireOwner(). */
export function adminClient() {
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_KEY!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
```

`web/src/lib/auth.ts` :

```ts
export function isOwnerEmail(email: string | null | undefined, owner: string | undefined): boolean {
  if (!email || !owner) return false;
  return email.trim().toLowerCase() === owner.trim().toLowerCase();
}

/** À appeler en premier dans chaque action serveur : les Server Functions
 *  sont joignables par POST direct, la session est la seule protection. */
export async function requireOwner(): Promise<string> {
  const { createAuthClient } = await import("@/lib/supabase/server");
  const supabase = await createAuthClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email ?? null;
  if (!isOwnerEmail(email, process.env.OWNER_EMAIL)) {
    throw new Error("non_autorise");
  }
  return email!;
}
```

`web/src/lib/errors.ts` :

```ts
import { frDayMonth } from "./date";

type DbError = { code?: string; message?: string; details?: string } | null | undefined;

const DEFAULT = "Échec de l'enregistrement — réessaie.";

const UNAVAILABLE: Record<string, string> = {
  reserved_nearby: "Ce joueur est déjà réservé à moins de 30 jours de cette soirée.",
  playoffs_used: "Ce joueur a déjà été utilisé pendant ces playoffs.",
  team_eliminated: "Son équipe est éliminée.",
  not_qualified: "Son équipe n'est pas qualifiée pour les playoffs.",
};

/** Traduit les erreurs de la base (trigger picks_validate, contraintes x2)
 *  en messages lisibles. Ne renvoie jamais le message brut. */
export function pickErrorMessage(err: DbError): string {
  if (!err) return DEFAULT;
  const message = err.message ?? "";
  if (err.code === "P0001") {
    if (message.startsWith("player_unavailable:cooldown")) {
      return err.details
        ? `Joueur bloqué jusqu'au ${frDayMonth(err.details)} (cooldown de 30 jours).`
        : "Joueur bloqué par le cooldown de 30 jours.";
    }
    if (message.startsWith("player_unavailable:")) {
      return UNAVAILABLE[message.split(":")[1]] ?? "Ce joueur n'est pas disponible ce soir-là.";
    }
    if (message.startsWith("night_not_eligible")) return "Cette soirée ne compte pas pour la TTFL (présaison, play-in…).";
    if (message.startsWith("player_not_in_game")) return "Ce joueur ne joue pas ce match.";
    if (message.startsWith("date_mismatch")) return "La date ne correspond pas au match.";
    if (message.startsWith("game_not_found")) return "Match introuvable.";
  }
  if (err.code === "23505") {
    return message.includes("picks_x2_month") ? "Tu as déjà utilisé ton x2 ce mois-ci." : "Tu as déjà un pick ce soir-là.";
  }
  if (err.code === "23514" && message.includes("picks_x2_window")) {
    return "Le x2 n'existe qu'en saison régulière, de novembre à avril.";
  }
  return DEFAULT;
}
```

- [ ] **Step 5: Vérifier**

Run: `cd web && npm test && npx tsc --noEmit && npm run lint`
Expected: tests PASS (date 5, auth 2, errors 6) ; tsc et lint sans erreur.

- [ ] **Step 6: Commiter**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/src/lib
git commit -m "feat(web): fondations — soirée du deck (Paris), clients Supabase, auth propriétaire, erreurs"
```

---

### Task 4: Connexion par code e-mail et rafraîchissement de session

**Files:**
- Create: `web/src/proxy.ts`, `web/src/app/connexion/page.tsx`, `web/src/app/connexion/LoginForm.tsx`, `web/src/app/connexion/actions.ts`

**Interfaces:**
- Consumes: `createAuthClient`, `isOwnerEmail` (tâche 3).
- Produces:
  - `sendCode(email: string): Promise<{ ok: boolean; error?: string }>` ;
  - `verifyCode(email: string, code: string): Promise<{ ok: boolean; error?: string }>` ;
  - page `/connexion` ;
  - `proxy.ts` qui rafraîchit la session à chaque requête.

- [ ] **Step 1: Lire la doc Next 16**

Lire `web/node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md` et `01-app/02-guides/authentication.md`. Vérifier la convention `src/proxy.ts` (export `proxy`) et l'usage de `cookies()` dans une Server Function.

- [ ] **Step 2: Implémenter le proxy**

`web/src/proxy.ts` :

```ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/** Rafraîchit le jeton de session Supabase (les Server Components ne peuvent
 *  pas écrire de cookies). Pas d'autorisation ici : elle est faite par
 *  requireOwner() dans chaque action serveur. */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );
  await supabase.auth.getUser();
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|manifest.json|sw.js|workbox-.*|swe-worker-.*|icons/).*)"],
};
```

- [ ] **Step 3: Implémenter les actions de connexion**

`web/src/app/connexion/actions.ts` :

```ts
"use server";

import { isOwnerEmail } from "@/lib/auth";
import { createAuthClient } from "@/lib/supabase/server";

/** Envoie un code à 6 chiffres (modèle d'e-mail Supabase avec {{ .Token }}).
 *  Réponse identique pour un e-mail non autorisé : on ne révèle rien. */
export async function sendCode(email: string): Promise<{ ok: boolean; error?: string }> {
  const clean = email.trim().toLowerCase();
  if (!isOwnerEmail(clean, process.env.OWNER_EMAIL)) return { ok: true };
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.signInWithOtp({ email: clean, options: { shouldCreateUser: false } });
  return error ? { ok: false, error: "Envoi impossible pour le moment, réessaie dans quelques minutes." } : { ok: true };
}

export async function verifyCode(email: string, code: string): Promise<{ ok: boolean; error?: string }> {
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.verifyOtp({ email: email.trim().toLowerCase(), token: code.trim(), type: "email" });
  return error ? { ok: false, error: "Code invalide ou expiré." } : { ok: true };
}
```

- [ ] **Step 4: Implémenter la page**

`web/src/app/connexion/page.tsx` :

```tsx
import LoginForm from "./LoginForm";

export default function ConnexionPage() {
  return (
    <div className="px-4 py-8 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        CONNE<span className="flame-text">XION</span>
      </h1>
      <p className="text-sm text-[color:var(--color-text-mute)] mt-2">
        Un code à 6 chiffres t&apos;est envoyé par e-mail. Il ouvre une session sur cet appareil.
      </p>
      <LoginForm />
    </div>
  );
}
```

`web/src/app/connexion/LoginForm.tsx` :

```tsx
"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { sendCode, verifyCode } from "./actions";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"email" | "code">("email");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const submitEmail = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await sendCode(email);
      if (res.ok) setStep("code");
      else setError(res.error ?? null);
    });
  };

  const submitCode = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await verifyCode(email, code);
      if (res.ok) {
        router.push("/");
        router.refresh();
      } else setError(res.error ?? null);
    });
  };

  const input = "w-full mt-2 px-4 py-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/10 text-white";
  const button = "w-full mt-4 py-3 rounded-[var(--radius-card)] font-display text-xl tracking-[0.15em] text-white bg-[color:var(--color-flame)] disabled:opacity-50";

  return step === "email" ? (
    <form onSubmit={submitEmail} className="mt-6">
      <label className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">E-mail</label>
      <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      <button disabled={pending} className={button}>{pending ? "…" : "RECEVOIR UN CODE"}</button>
      {error && <p role="alert" className="mt-2 text-xs text-[color:var(--color-crimson)]">{error}</p>}
    </form>
  ) : (
    <form onSubmit={submitCode} className="mt-6">
      <label className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">Code reçu par e-mail</label>
      <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} required value={code}
             onChange={(e) => setCode(e.target.value)} className={`${input} tracking-[0.5em] text-center text-2xl`} />
      <button disabled={pending} className={button}>{pending ? "…" : "VALIDER"}</button>
      {error && <p role="alert" className="mt-2 text-xs text-[color:var(--color-crimson)]">{error}</p>}
      <button type="button" onClick={() => setStep("email")} className="w-full mt-3 text-xs text-[color:var(--color-text-mute)] underline">
        Changer d&apos;e-mail / renvoyer un code
      </button>
    </form>
  );
}
```

- [ ] **Step 5: Vérifier**

Run: `cd web && npx tsc --noEmit && npm run lint && npm run build`
Expected: pas d'erreur. La sortie du build liste la route `/connexion` et un proxy (« ƒ Proxy » ou équivalent).

- [ ] **Step 6: Commiter**

```bash
git add web/src/proxy.ts web/src/app/connexion
git commit -m "feat(web): connexion par code e-mail et rafraîchissement de session"
```

---

### Task 5: Actions serveur (picks, x2, Seconde chance, favoris)

**Files:**
- Create: `web/src/app/actions.ts`

**Interfaces:**
- Consumes: `requireOwner`, `adminClient`, `pickErrorMessage`, `deckDate`, `addDays` (tâche 3).
- Produces (tous `Promise<ActionResult>` avec `ActionResult = { ok: true } | { ok: false; error: string }`) :
  - `savePick({ date, playerId, gameId })` ;
  - `setX2({ date, value })` ;
  - `addSecondChance({ pickId, boughtOn })` ;
  - `setWatchlist({ playerId, priority: 1 | 2 | 3 | null })` ;
  - `signOut()`.

- [ ] **Step 1: Implémenter**

`web/src/app/actions.ts` :

```ts
"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { addDays, deckDate } from "@/lib/date";
import { pickErrorMessage } from "@/lib/errors";
import { adminClient } from "@/lib/supabase/admin";
import { createAuthClient } from "@/lib/supabase/server";

export type ActionResult = { ok: true } | { ok: false; error: string };

const RESERVATION_DAYS = 14; // R9
const SECOND_CHANCE_DAYS = 7; // R15

async function owner(): Promise<ActionResult | null> {
  try {
    await requireOwner();
    return null;
  } catch {
    return { ok: false, error: "Connecte-toi pour enregistrer (menu Picks → Connexion)." };
  }
}

function refresh(playerId?: number) {
  revalidatePath("/");
  revalidatePath("/deck");
  revalidatePath("/picks");
  if (playerId) revalidatePath(`/player/${playerId}`);
}

/** R2 : un pick par soirée ; s'il existe, on remplace le joueur (UPDATE,
 *  revalidé par le trigger picks_validate). R9 : 14 jours d'avance max. */
export async function savePick(input: { date: string; playerId: number; gameId: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const today = deckDate();
  if (input.date < today) return { ok: false, error: "Cette soirée est passée." };
  if (input.date > addDays(today, RESERVATION_DAYS)) {
    return { ok: false, error: "Réservation possible jusqu'à 14 jours à l'avance." };
  }
  const db = adminClient();
  const { data: existing, error: readError } = await db.from("picks").select("id").eq("date", input.date).maybeSingle();
  if (readError) return { ok: false, error: pickErrorMessage(readError) };
  const { error } = existing
    ? await db.from("picks").update({ player_id: input.playerId, game_id: input.gameId }).eq("id", existing.id)
    : await db.from("picks").insert({ player_id: input.playerId, game_id: input.gameId, date: input.date });
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh(input.playerId);
  return { ok: true };
}

/** R10 : activable jusqu'à la fermeture (soirée ≥ aujourd'hui) ; l'unicité
 *  mensuelle et la fenêtre novembre-avril sont garanties par la base. */
export async function setX2(input: { date: string; value: boolean }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  if (input.date < deckDate()) return { ok: false, error: "Le x2 ne se modifie plus après la fermeture." };
  const { error } = await adminClient().from("picks").update({ is_x2: input.value }).eq("date", input.date);
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh();
  return { ok: true };
}

/** R15 : débloque le pick à 0 visé, du jour d'achat à achat + 7 jours. */
export async function addSecondChance(input: { pickId: number; boughtOn: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const db = adminClient();
  const { data: pick, error: readError } = await db.from("picks")
    .select("id, player_id, actual_score").eq("id", input.pickId).maybeSingle();
  if (readError || !pick) return { ok: false, error: "Pick introuvable." };
  if (pick.actual_score !== 0) return { ok: false, error: "La Seconde chance ne s'applique qu'à un pick à 0." };
  const { error } = await db.from("second_chances").insert({
    pick_id: pick.id, player_id: pick.player_id,
    bought_on: input.boughtOn, expires_on: addDays(input.boughtOn, SECOND_CHANCE_DAYS),
  });
  if (error) return { ok: false, error: error.code === "23505" ? "Seconde chance déjà enregistrée pour ce pick." : pickErrorMessage(error) };
  refresh(pick.player_id);
  return { ok: true };
}

/** Favoris (sans effet sur le moteur). */
export async function setWatchlist(input: { playerId: number; priority: 1 | 2 | 3 | null }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const db = adminClient();
  const { error } = input.priority === null
    ? await db.from("player_watchlist").delete().eq("player_id", input.playerId)
    : await db.from("player_watchlist").upsert({ player_id: input.playerId, priority: input.priority });
  if (error) return { ok: false, error: "Échec de la mise à jour des favoris." };
  revalidatePath(`/player/${input.playerId}`);
  return { ok: true };
}

export async function signOut(): Promise<ActionResult> {
  const supabase = await createAuthClient();
  await supabase.auth.signOut();
  refresh();
  return { ok: true };
}
```

- [ ] **Step 2: Vérifier**

Run: `cd web && npx tsc --noEmit && npm run lint`
Expected: pas d'erreur.

Relecture obligatoire : chaque action d'écriture commence bien par `owner()`, et `adminClient` n'est importé que dans ce fichier : `grep -rn "adminClient" web/src` → `lib/supabase/admin.ts` et `app/actions.ts` seulement.

- [ ] **Step 3: Commiter**

```bash
git add web/src/app/actions.ts
git commit -m "feat(web): actions serveur authentifiées (pick R2/R9, x2, Seconde chance, favoris)"
```

---

### Task 6: Écran « Ce soir »

**Files:**
- Create: `web/src/lib/display.ts`, `web/src/lib/display.test.ts`, `web/src/components/MyPickCard.tsx`
- Modify: `web/src/app/page.tsx`, `web/src/components/RecommendationCard.tsx`, `web/src/components/PlayerList.tsx`, `web/src/components/GamesCollapsible.tsx`, `web/src/components/NoPickBanner.tsx`, `web/src/types/index.ts`

**Interfaces:**
- Consumes: `supabase` (public), `deckDate`, `frLongDate`, `frDayMonth`, `parisTime` (tâche 3), `setX2` (tâche 5).
- Produces:
  - `recMeta(rec) -> { pPlay: string | null; value: string | null; lockedUntil: string | null; bestFuture: string | null }` ;
  - `homeState({ hasNight, recCount, hasPick }) -> "no_games" | "waiting_sync" | "picked" | "to_pick"` ;
  - type `Recommendation` enrichi (`projection`, `p_play`, `value`, `lock_value`, `locked_until`, `best_future`, tous `… | null`) ;
  - type `Night` ;
  - `Pick` enrichi (`season`, `is_x2`).

- [ ] **Step 1: Écrire les tests des helpers d'affichage**

`web/src/lib/display.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { homeState, recMeta } from "./display";

describe("recMeta", () => {
  it("formate les colonnes S1", () => {
    expect(recMeta({ p_play: 0.55, value: 31.24, locked_until: "2026-12-02", best_future: "vendredi 20/11 @ WAS · 50 pts projetés" }))
      .toEqual({ pPlay: "55 %", value: "31.2", lockedUntil: "02/12", bestFuture: "vendredi 20/11 @ WAS · 50 pts projetés" });
  });
  it("ne plante pas sur une ligne antérieure à la migration 020", () => {
    expect(recMeta({ p_play: null, value: null, locked_until: null, best_future: null }))
      .toEqual({ pPlay: null, value: null, lockedUntil: null, bestFuture: null });
  });
});

describe("homeState", () => {
  it("pas de soirée", () => expect(homeState({ hasNight: false, recCount: 0, hasPick: false })).toBe("no_games"));
  it("soirée sans recos : on attend la synchro, jamais les recos d'hier", () =>
    expect(homeState({ hasNight: true, recCount: 0, hasPick: false })).toBe("waiting_sync"));
  it("pick déjà posé", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: true })).toBe("picked"));
  it("à picker", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: false })).toBe("to_pick"));
});
```

- [ ] **Step 2: Lancer pour constater l'échec**

Run: `cd web && npm test`
Expected: FAIL (`./display` introuvable).

- [ ] **Step 3: Implémenter les helpers et les types**

`web/src/lib/display.ts` :

```ts
import { frDayMonth } from "./date";

type RecS1 = { p_play: number | null; value: number | null; locked_until: string | null; best_future: string | null };

export function recMeta(rec: RecS1) {
  return {
    pPlay: rec.p_play === null ? null : `${Math.round(rec.p_play * 100)} %`,
    value: rec.value === null ? null : rec.value.toFixed(1),
    lockedUntil: rec.locked_until ? frDayMonth(rec.locked_until) : null,
    bestFuture: rec.best_future,
  };
}

export function homeState(s: { hasNight: boolean; recCount: number; hasPick: boolean }) {
  if (!s.hasNight) return "no_games" as const;
  if (s.hasPick) return "picked" as const;
  if (s.recCount === 0) return "waiting_sync" as const;
  return "to_pick" as const;
}
```

Dans `web/src/types/index.ts` :
- ajouter à `Recommendation` : `projection: number | null; p_play: number | null; value: number | null; lock_value: number | null; locked_until: string | null; best_future: string | null;` ;
- ajouter à `Pick` : `season: string; is_x2: boolean;` ;
- ajouter :

```ts
export interface Night {
  date: string;
  season: string;
  mode: "regular" | "playoffs";
  n_eligible_games: number;
  closing_at: string;
  is_phantom: boolean;
}
```

- retirer `matchup?` de `RecommendationWithPlayer` (les types `MatchupAggregate`, `WeeklyPlanEntry`, `Series`, `SeriesForecast` sont supprimés en tâche 9).

- [ ] **Step 4: Réécrire la carte de reco et les composants liés**

Dans `web/src/components/RecommendationCard.tsx` :
- supprimer `MatchupLine`, `isElimCritical` et les puces `ELIMINATION`, `SERIE CRITIQUE`, `USAGE+`, `VOLATILE` ;
- supprimer l'affichage `G{game.game_number}` ;
- garder les puces `HOME` et `EN FORME` (tag `hot`), et ajouter une puce `B2B` (tag `b2b`) et une puce `RISQUE` (tag `dnp_risk`), sur le modèle des autres `TagChip` ;
- remplacer le libellé « Score estimé » par « Espérance » ;
- sous la ligne verdict, ajouter :

```tsx
{(() => {
  const m = recMeta(rec);
  if (!m.pPlay && !m.lockedUntil) return null;
  return (
    <p className="mt-2 text-[11px] tracking-wide text-[color:var(--color-text-mute)]">
      {m.pPlay && <>Joue à <span className="text-[color:var(--color-text-soft)] font-semibold">{m.pPlay}</span></>}
      {m.value && <> · valeur <span className="text-[color:var(--color-text-soft)] font-semibold">{m.value}</span></>}
      {m.lockedUntil && <> · bloqué jusqu&apos;au {m.lockedUntil}</>}
      {m.bestFuture && <><br />Meilleur soir à venir : {m.bestFuture}</>}
    </p>
  );
})()}
```

(importer `recMeta` depuis `@/lib/display`).

Dans `web/src/components/GamesCollapsible.tsx` :
- retirer la prop `series`, `getSeriesForGame`, l'affichage `G{game_number}` et le score de série ;
- dans `formatTipOff`, passer `timeZone: "Europe/Paris"` à `toLocaleTimeString` (corrige l'écart d'hydratation, audit §4).

Dans `web/src/components/NoPickBanner.tsx` : supprimer la prop inutilisée `todayDate`.

`web/src/components/MyPickCard.tsx` :

```tsx
"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { setX2 } from "@/app/actions";

export default function MyPickCard({
  date, playerId, playerName, team, isX2, x2Allowed,
}: {
  date: string; playerId: number; playerName: string; team: string; isX2: boolean; x2Allowed: boolean;
}) {
  const [x2, setLocalX2] = useState(isX2);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const toggle = () => {
    setError(null);
    startTransition(async () => {
      const res = await setX2({ date, value: !x2 });
      if (res.ok) setLocalX2(!x2);
      else setError(res.error);
    });
  };

  return (
    <div className="mx-3 mt-3 rounded-[var(--radius-card)] border border-[color:var(--color-emerald)]/40 bg-[color:var(--color-emerald)]/10 px-4 py-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--color-emerald)]">Ton pick de ce soir</div>
      <div className="flex items-center justify-between gap-3 mt-1">
        <Link href={`/player/${playerId}`} className="font-display text-2xl text-white tracking-wide truncate">
          {playerName} <span className="text-sm text-[color:var(--color-text-mute)]">{team}</span>
        </Link>
        {x2Allowed && (
          <button onClick={toggle} disabled={pending}
                  className={`shrink-0 px-3 py-1 rounded-full text-xs font-bold border ${x2
                    ? "bg-[color:var(--color-gold)] text-black border-[color:var(--color-gold)]"
                    : "border-white/15 text-[color:var(--color-text-soft)]"}`}>
            {pending ? "…" : x2 ? "x2 ACTIVÉ" : "ACTIVER x2"}
          </button>
        )}
      </div>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1">
        Tu peux le remplacer jusqu&apos;à la fermeture : choisis un autre joueur ci-dessous.
      </p>
      {error && <p role="alert" className="mt-1 text-xs text-[color:var(--color-crimson)]">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Réécrire la page**

`web/src/app/page.tsx` (remplace le fichier) :

```tsx
import { supabase } from "@/lib/supabase/public";
import { Game, Night, Pick, Player, Recommendation, RecommendationWithPlayer, SyncLog } from "@/types";
import SyncStatus from "@/components/SyncStatus";
import NoPickBanner from "@/components/NoPickBanner";
import GamesCollapsible from "@/components/GamesCollapsible";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";
import RefreshButton from "@/components/RefreshButton";
import MyPickCard from "@/components/MyPickCard";
import { deckDate, frLongDate, parisTime } from "@/lib/date";
import { homeState } from "@/lib/display";

export const revalidate = 0;

// Garde-fou d'affichage (pas une règle) : un joueur passé « Out » après la
// dernière synchro ne doit pas rester en tête. Miroir de HARD_OUT_STATUSES
// (engine/stats/availability_prob.py).
const HARD_OUT_STATUSES = new Set(["Out", "Doubtful", "Out For Season", "Suspended"]);
const X2_MONTHS = new Set([11, 12, 1, 2, 3, 4]);

async function getData() {
  const deck = deckDate();
  const [nightRes, gamesRes, recsRes, pickRes, syncRes] = await Promise.all([
    supabase.from("nights").select("*").eq("date", deck).maybeSingle(),
    supabase.from("games").select("*").eq("date", deck).order("tip_off"),
    supabase.from("recommendations").select("*").eq("date", deck).order("rank"),
    supabase.from("picks").select("*").eq("date", deck).maybeSingle(),
    supabase.from("sync_log").select("*").eq("job", "daily_sync").order("started_at", { ascending: false }).limit(1),
  ]);
  const night = (nightRes.data as Night | null) ?? null;
  const games = ((gamesRes.data || []) as Game[]).filter((g) =>
    ["regular", "cup_final", "playoffs"].includes((g as Game & { game_type?: string }).game_type ?? "regular"));
  const recs = (recsRes.data || []) as Recommendation[];
  const pick = (pickRes.data as Pick | null) ?? null;

  const ids = [...new Set([...recs.map((r) => r.player_id), ...(pick ? [pick.player_id] : [])])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [] };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  const recsWithPlayers = recs
    .map((r) => {
      const player = players.get(r.player_id);
      const game = games.find((g) => g.home_team === player?.team || g.away_team === player?.team);
      if (!player || !game || (player.injury_status && HARD_OUT_STATUSES.has(player.injury_status))) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  return {
    deck, night, games, recsWithPlayers, pick,
    pickPlayer: pick ? players.get(pick.player_id) ?? null : null,
    sync: (syncRes.data?.[0] || null) as SyncLog | null,
  };
}

export default async function TonightPage() {
  const { deck, night, games, recsWithPlayers, pick, pickPlayer, sync } = await getData();
  const state = homeState({ hasNight: !!night && night.n_eligible_games > 0, recCount: recsWithPlayers.length, hasPick: !!pick });
  const top3 = recsWithPlayers.slice(0, 3);
  const month = Number(deck.slice(5, 7));

  return (
    <div className="animate-fade-in">
      <header className="relative overflow-hidden px-4 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3 relative">
          <div className="min-w-0">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-gold)] animate-live-dot" />
              {night?.mode === "playoffs" ? "Playoffs" : "Saison régulière"}
              {night && <> · fermeture {parisTime(night.closing_at)}</>}
            </span>
            <h1 className="font-display text-5xl leading-none tracking-wide text-white">
              CE <span className="flame-text">SOIR</span>
            </h1>
            <p className="text-xs text-[color:var(--color-text-mute)] mt-1.5 capitalize tracking-wide">
              {frLongDate(deck)} ·{" "}
              <span className="text-[color:var(--color-text-soft)] font-semibold">
                {games.length} match{games.length > 1 ? "s" : ""}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 pt-1">
            <RefreshButton />
          </div>
        </div>
      </header>

      {pick && pickPlayer ? (
        <MyPickCard date={deck} playerId={pickPlayer.id} playerName={pickPlayer.name} team={pickPlayer.team}
                    isX2={pick.is_x2} x2Allowed={pick.mode === "regular" && X2_MONTHS.has(month)} />
      ) : (
        <NoPickBanner hasGamesTonight={state !== "no_games"} hasPickToday={false} />
      )}

      <SyncStatus sync={sync} />

      <div className="mt-3 px-3">
        <GamesCollapsible games={games} />
      </div>

      <section id="top-3" className="mt-6 px-3">
        <div className="flex items-end justify-between mb-3 px-1">
          <h2 className="font-display text-3xl tracking-wide text-white leading-none">
            TOP <span className="gold-text">3</span>
          </h2>
          <span className="text-[10px] tracking-[0.2em] uppercase text-[color:var(--color-text-mute)] pb-1">
            {state === "picked" ? "Alternatives pour remplacer" : "Picks du soir"}
          </span>
        </div>
        <div className="flex flex-col gap-3 stagger">
          {top3.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)}
          {top3.length === 0 && (
            <div className="surface p-8 text-center">
              <div className="font-display text-2xl text-[color:var(--color-text-mute)] mb-1">
                {state === "no_games" ? "Pas de soirée TTFL" : "Aucune reco"}
              </div>
              <p className="text-sm text-[color:var(--color-text-mute)]">
                {state === "no_games" ? "Aucun match éligible ce soir." : "Prochaine synchro en cours…"}
              </p>
            </div>
          )}
        </div>
      </section>

      <PlayerList recs={recsWithPlayers} />
    </div>
  );
}
```

Note : si le type `Game` n'a pas `game_type`, l'ajouter dans `types/index.ts` (`game_type: string; season: string;`) plutôt que le cast local, et simplifier le filtre en `g.game_type`.

- [ ] **Step 6: Vérifier**

Run: `cd web && npm test && npx tsc --noEmit && npm run lint`
Expected: PASS. Les erreurs de compilation restantes dans les pages PO (strategy, series, WatchlistAlerts…) sont traitées en tâche 9. Si `tsc` en signale, les noter dans le rapport et ne corriger que les fichiers de cette tâche.

- [ ] **Step 7: Commiter**

```bash
git add web/src/lib/display.ts web/src/lib/display.test.ts web/src/components web/src/app/page.tsx web/src/types/index.ts
git commit -m "feat(web): écran « Ce soir » sur la soirée du deck, espérance complète, ton pick et x2"
```

---

### Task 7: Fiche joueur : disponibilité, prochains soirs, pick et réservation

**Files:**
- Create: `web/src/app/player/[id]/PickControls.tsx`
- Modify: `web/src/app/player/[id]/page.tsx`, `web/src/app/player/[id]/WatchlistStar.tsx`
- Delete: `web/src/app/player/[id]/PickButton.tsx`

**Interfaces:**
- Consumes: RPC `player_calendar` (tâche 2), `savePick`, `setWatchlist` (tâche 5), `deckDate`, `addDays`, `frLongDate`, `frDayMonth` (tâche 3).
- Produces: `PickControls({ playerId, nights })` avec `nights: CalendarNight[]` et `CalendarNight = { night, game_id, opponent, is_home, ok, available_from, reason, closing_at }`.

- [ ] **Step 1: Implémenter `PickControls`**

`web/src/app/player/[id]/PickControls.tsx` :

```tsx
"use client";

import { useState, useTransition } from "react";
import { savePick } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";

export type CalendarNight = {
  night: string; game_id: string; opponent: string; is_home: boolean;
  ok: boolean; available_from: string | null; reason: string | null; closing_at: string;
};

const REASON: Record<string, string> = {
  reserved_nearby: "réservé à moins de 30 jours",
  playoffs_used: "déjà utilisé en playoffs",
  team_eliminated: "équipe éliminée",
  not_qualified: "équipe non qualifiée",
};

export default function PickControls({
  playerId, nights, today, lastBookable,
}: { playerId: number; nights: CalendarNight[]; today: string; lastBookable: string }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, startTransition] = useTransition();

  const book = (n: CalendarNight) => {
    setMsg(null);
    startTransition(async () => {
      const res = await savePick({ date: n.night, playerId, gameId: n.game_id });
      setMsg(res.ok
        ? { ok: true, text: n.night === today ? "Pické pour ce soir." : `Réservé pour le ${frDayMonth(n.night)}.` }
        : { ok: false, text: res.error });
    });
  };

  if (nights.length === 0) {
    return <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL pour son équipe dans les 30 prochains jours.</p>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {nights.map((n) => {
        const bookable = n.ok && n.night <= lastBookable;
        const status = n.ok
          ? "disponible"
          : n.reason === "cooldown" && n.available_from
            ? `dispo le ${frDayMonth(n.available_from)}`
            : REASON[n.reason ?? ""] ?? "indisponible";
        return (
          <div key={n.night} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
            <div className="min-w-0">
              <div className="text-sm text-[color:var(--color-text)] capitalize">
                {n.night === today ? "Ce soir" : frLongDate(n.night)} · {n.is_home ? "vs" : "@"} {n.opponent}
              </div>
              <div className={`text-[11px] ${n.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text-mute)]"}`}>{status}</div>
            </div>
            {bookable && (
              <button onClick={() => book(n)} disabled={pending}
                      className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
                {n.night === today ? "PICKER" : "RÉSERVER"}
              </button>
            )}
          </div>
        );
      })}
      {msg && <p role="alert" className={`mt-1 text-xs ${msg.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-crimson)]"}`}>{msg.text}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Réécrire la page**

Dans `web/src/app/player/[id]/page.tsx` :
- passer à `export const revalidate = 0;` ;
- supprimer `planDate`, `weekly_plan`, `isFuturePlan`, `WeeklyPlanEntry`, `PickButton`, les références à `G{gameNumber}` et le badge « Calé pour » ;
- remplacer `getData` par :

```tsx
async function getData(playerId: number) {
  const today = deckDate();
  const [playerRes, recRes, calRes, watchlistRes] = await Promise.all([
    supabase.from("players").select("*").eq("id", playerId).single(),
    supabase.from("recommendations").select("*").eq("player_id", playerId).eq("date", today).maybeSingle(),
    supabase.rpc("player_calendar", { p_player_id: playerId, p_from: today, p_to: addDays(today, 29) }),
    supabase.from("player_watchlist").select("*").eq("player_id", playerId).maybeSingle(),
  ]);
  return {
    today,
    player: playerRes.data as Player | null,
    rec: (recRes.data as Recommendation | null) ?? null,
    nights: (calRes.data || []) as CalendarNight[],
    watchlist: (watchlistRes.data as WatchlistEntry | null) ?? null,
  };
}
```

- dans le rendu, l'adversaire et le domicile de ce soir viennent de `nights.find((n) => n.night === today)`. Le score affiché devient `rec?.estimated_score` avec le libellé « Espérance », et `recMeta(rec)` ajoute les mêmes lignes S1 que la carte de reco quand `rec` existe ;
- remplacer le bloc « pick cta » par :

```tsx
<section className="mt-6">
  <h2 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2">
    Ses soirées (30 jours)
  </h2>
  <PickControls playerId={player.id} nights={nights} today={today} lastBookable={addDays(today, 14)} />
</section>
```

- `searchParams` n'est plus utilisé : retirer ce paramètre de la signature de la page.

Dans `WatchlistStar.tsx` : remplacer les appels `supabase.from("player_watchlist")…` par `const res = await setWatchlist({ playerId, priority: next });`, puis revenir à l'état précédent et `setError(res.error)` si `!res.ok`. Retirer l'import de `supabase`.

`git rm web/src/app/player/[id]/PickButton.tsx`.

- [ ] **Step 3: Vérifier**

Run: `cd web && npx tsc --noEmit && npm run lint && npm test`
Expected: pas d'erreur dans les fichiers de la tâche (les pages PO restantes sont traitées en tâche 9).

- [ ] **Step 4: Commiter**

```bash
git add web/src/app/player
git commit -m "feat(web): fiche joueur — disponibilité, soirées à 30 jours, pick et réservation"
```

---

### Task 8: Picks : statistiques de saison et historique

**Files:**
- Create: `web/src/app/picks/PicksHistory.tsx`
- Modify: `web/src/app/picks/page.tsx`
- Delete: `web/src/app/picks/PicksTabs.tsx`

**Interfaces:**
- Consumes: RPC `period_stats` (tâche 2), `addSecondChance`, `signOut` (tâche 5), `createAuthClient` (tâche 3), `deckDate`, `seasonForDate`, `frLongDate`, `frDayMonth`.
- Produces: page `/picks` avec les stats de la saison en cours (moyenne R14), l'historique (x2 réel via `is_x2`, zéros, bouton Seconde chance) et un lien Connexion / Déconnexion.

- [ ] **Step 1: Implémenter l'historique**

`web/src/app/picks/PicksHistory.tsx` :

```tsx
"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { addSecondChance } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";

export type HistoryRow = {
  id: number; date: string; player_id: number; player_name: string; team: string;
  actual_score: number | null; is_x2: boolean; has_second_chance: boolean;
};

export default function PicksHistory({ rows, today }: { rows: HistoryRow[]; today: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const secondChance = (id: number) => {
    setMsg(null);
    startTransition(async () => {
      const res = await addSecondChance({ pickId: id, boughtOn: today });
      setMsg(res.ok ? "Seconde chance enregistrée : repick possible pendant 7 jours." : res.error);
    });
  };

  return (
    <ol className="flex flex-col gap-1.5">
      {rows.map((r) => {
        const points = r.actual_score === null ? null : r.actual_score * (r.is_x2 ? 2 : 1);
        return (
          <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
            <div className="min-w-0">
              <Link href={`/player/${r.player_id}`} className="text-sm font-semibold text-[color:var(--color-text)] truncate block">
                {r.player_name} <span className="text-[11px] text-[color:var(--color-text-mute)]">{r.team}</span>
              </Link>
              <div className="text-[11px] text-[color:var(--color-text-mute)] capitalize">
                {r.date > today ? `réservé · ${frLongDate(r.date)}` : frLongDate(r.date)}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-display text-xl leading-none font-mono-num text-[color:var(--color-text)]">
                {points === null ? "—" : points}
                {r.is_x2 && <span className="ml-1 text-xs text-[color:var(--color-gold)]">x2</span>}
              </div>
              {r.actual_score === 0 && !r.has_second_chance && (
                <button onClick={() => secondChance(r.id)} disabled={pending}
                        className="mt-1 text-[10px] underline text-[color:var(--color-text-soft)]">
                  Seconde chance
                </button>
              )}
              {r.has_second_chance && <div className="mt-1 text-[10px] text-[color:var(--color-emerald)]">2de chance · {frDayMonth(r.date)}</div>}
            </div>
          </li>
        );
      })}
      {msg && <p role="alert" className="text-xs text-[color:var(--color-text-soft)]">{msg}</p>}
    </ol>
  );
}
```

- [ ] **Step 2: Réécrire la page**

`web/src/app/picks/page.tsx` :

```tsx
import Link from "next/link";
import { supabase } from "@/lib/supabase/public";
import { createAuthClient } from "@/lib/supabase/server";
import { isOwnerEmail } from "@/lib/auth";
import { deckDate, seasonForDate } from "@/lib/date";
import PicksHistory, { HistoryRow } from "./PicksHistory";
import SignOutButton from "./SignOutButton";

export const revalidate = 0;

type Stats = { nights: number; scored_nights: number; total: number; average: number | null; picks: number; zeros: number; x2_used: number };

export default async function PicksPage() {
  const today = deckDate();
  const season = seasonForDate(today);
  const auth = await createAuthClient();
  const { data: userData } = await auth.auth.getUser();
  const signedIn = isOwnerEmail(userData.user?.email, process.env.OWNER_EMAIL);

  const [statsRes, picksRes, scRes] = await Promise.all([
    supabase.rpc("period_stats", { p_season: season, p_mode: "regular", p_until: today }),
    supabase.from("picks").select("id, date, player_id, actual_score, is_x2, players(name, team)").eq("season", season).order("date", { ascending: false }),
    supabase.from("second_chances").select("pick_id"),
  ]);
  const stats = ((statsRes.data || [])[0] ?? null) as Stats | null;
  const withSc = new Set(((scRes.data || []) as { pick_id: number }[]).map((s) => s.pick_id));
  type Row = { id: number; date: string; player_id: number; actual_score: number | null; is_x2: boolean; players: { name: string; team: string } | null };
  const rows: HistoryRow[] = ((picksRes.data || []) as unknown as Row[]).map((p) => ({
    id: p.id, date: p.date, player_id: p.player_id, player_name: p.players?.name ?? `#${p.player_id}`,
    team: p.players?.team ?? "", actual_score: p.actual_score, is_x2: p.is_x2, has_second_chance: withSc.has(p.id),
  }));

  return (
    <div className="px-4 py-5 animate-fade-in">
      <div className="flex items-start justify-between">
        <h1 className="font-display text-4xl leading-none tracking-wide text-white">
          MES <span className="flame-text">PICKS</span>
        </h1>
        {signedIn ? <SignOutButton /> : (
          <Link href="/connexion" className="text-xs underline text-[color:var(--color-text-soft)]">Connexion</Link>
        )}
      </div>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1 uppercase tracking-[0.18em]">Saison {season}</p>

      <div className="grid grid-cols-3 gap-2 mt-4">
        {[
          { label: "Moyenne", value: stats?.average ?? "—" },
          { label: "Soirées", value: stats?.nights ?? 0 },
          { label: "Zéros", value: stats?.zeros ?? 0 },
        ].map((t) => (
          <div key={t.label} className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-2 py-3 text-center">
            <div className="font-display text-2xl leading-none text-white font-mono-num">{t.value}</div>
            <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-1.5">{t.label}</div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[color:var(--color-text-mute)] mt-2">
        Moyenne sur toutes les soirées éligibles : une soirée sans pick compte 0. x2 utilisés : {stats?.x2_used ?? 0}.
      </p>

      <div className="mt-5">
        <PicksHistory rows={rows} today={today} />
      </div>
    </div>
  );
}
```

Créer `web/src/app/picks/SignOutButton.tsx` :

```tsx
"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "@/app/actions";

export default function SignOutButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button onClick={() => startTransition(async () => { await signOut(); router.refresh(); })}
            disabled={pending} className="text-xs underline text-[color:var(--color-text-soft)]">
      Déconnexion
    </button>
  );
}
```

`git rm web/src/app/picks/PicksTabs.tsx`.

- [ ] **Step 3: Vérifier**

Run: `cd web && npx tsc --noEmit && npm run lint && npm test`
Expected: pas d'erreur dans les fichiers de la tâche.

- [ ] **Step 4: Commiter**

```bash
git add web/src/app/picks
git commit -m "feat(web): picks — moyenne sur toutes les soirées, x2 réel, Seconde chance, connexion"
```

---

### Task 9: Nettoyage des écrans playoffs, navigation, matchs, CI front

**Files:**
- Delete: `web/src/app/strategy/` (tout), `web/src/app/series/` (tout), `web/src/components/WatchlistAlerts.tsx`, `StrategyBanner.tsx`, `InjuryArbitrage.tsx`
- Modify: `web/src/types/index.ts`, `web/src/components/BottomNav.tsx`, `web/src/app/games/page.tsx`, `.github/workflows/ci.yml`, et tout fichier qui référence encore les éléments supprimés

**Interfaces:**
- Produces: navigation « Ce soir · Deck · Matchs · Picks · Blessés » ; `/games` limité à −7/+7 jours autour de `todayNBA()`, sans logique de série ; CI front.

- [ ] **Step 1: Supprimer les écrans et types PO**

```bash
git rm -r -q web/src/app/strategy web/src/app/series web/src/components/WatchlistAlerts.tsx web/src/components/StrategyBanner.tsx web/src/components/InjuryArbitrage.tsx
```

Dans `web/src/types/index.ts`, supprimer `Series`, `SeriesForecast`, `WeeklyPlanEntry`, `MatchupAggregate`, et `series_id` / `game_number` de `Game` s'ils ne sont plus lus. Ajouter `game_type: string; season: string;` à `Game` si ce n'est pas déjà fait (tâche 6).

- [ ] **Step 2: Navigation**

Dans `web/src/components/BottomNav.tsx`, remplacer l'onglet Stratégie par le Deck :

```tsx
const tabs: Tab[] = [
  { href: "/", label: "Ce soir", icon: IconBall },
  { href: "/deck", label: "Deck", icon: IconChart },
  { href: "/games", label: "Matchs", icon: IconScore },
  { href: "/picks", label: "Picks", icon: IconList },
  { href: "/injuries", label: "Blessés", icon: IconMed },
];
```

- [ ] **Step 3: Page des matchs**

Dans `web/src/app/games/page.tsx`, remplacer `PLAYOFFS_START` et tout le filtre de séries par une fenêtre glissante :

```tsx
import { supabase } from "@/lib/supabase/public";
import { Game } from "@/types";
import { addDays, todayNBA } from "@/lib/date";
import GamesList from "./GamesList";

export const revalidate = 300;

async function getData() {
  const today = todayNBA();
  const { data } = await supabase.from("games").select("*")
    .gte("date", addDays(today, -7)).lte("date", addDays(today, 7))
    .in("game_type", ["regular", "cup_final", "playoffs"])
    .order("date", { ascending: false }).limit(300);
  return { games: (data || []) as Game[] };
}
```

(le reste du composant `GamesPage` est inchangé).

Corriger toute autre référence cassée (`/games/[gameId]`, `GamesList`, etc.) avec le minimum de changement, et la noter dans le rapport.

- [ ] **Step 4: CI front**

Ajouter à `.github/workflows/ci.yml` un second job :

```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    env:
      NEXT_PUBLIC_SUPABASE_URL: http://localhost
      NEXT_PUBLIC_SUPABASE_ANON_KEY: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npx tsc --noEmit
      - run: npm test
      - run: npm run build
```

- [ ] **Step 5: Vérifier l'ensemble**

Run: `cd web && npm run lint && npx tsc --noEmit && npm test && NEXT_PUBLIC_SUPABASE_URL=http://localhost NEXT_PUBLIC_SUPABASE_ANON_KEY=test npm run build`
Expected: tout passe. Aucun import de `@/lib/supabase"` (ancien chemin), `weekly_plan`, `series_forecast`, `matchup_aggregates` : `grep -rn 'weekly_plan\|series_forecast\|matchup_aggregates\|lib/supabase"' web/src` ne renvoie rien.

- [ ] **Step 6: Commiter**

```bash
git add -A web .github/workflows/ci.yml
git commit -m "refactor(web): suppression des écrans playoffs, navigation Deck, matchs sur 14 jours, CI front"
```

---

### Task 10: Deck 14 jours

**Files:**
- Create: `web/src/app/deck/page.tsx`, `web/src/components/DeckNight.tsx`

**Interfaces:**
- Consumes: `nights`, vue `plan_latest` (tâche 2), `picks`, `players`, `savePick` (tâche 5), helpers de date (tâche 3).
- Produces: page `/deck` listant les 14 prochaines soirées. Pour chacune :
  - heure de fermeture ;
  - pick ou réservation existant, avec une alerte si le joueur est Out/Doubtful/Out For Season/Suspended ;
  - sinon la suggestion du plan, avec un bouton « Réserver » ;
  - alerte « soirée fantôme » (R13).

- [ ] **Step 1: Implémenter le composant**

`web/src/components/DeckNight.tsx` :

```tsx
"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { savePick } from "@/app/actions";
import { frLongDate, parisTime } from "@/lib/date";

export type DeckNightProps = {
  date: string; closingAt: string; nGames: number; isPhantom: boolean; isToday: boolean;
  pick: { playerId: number; name: string; team: string; injury: string | null; isX2: boolean } | null;
  suggestion: { playerId: number; name: string; team: string; gameId: string; projection: number; explanation: string } | null;
};

const HARD_OUT = new Set(["Out", "Doubtful", "Out For Season", "Suspended"]);

export default function DeckNight(p: DeckNightProps) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const reserve = () => {
    if (!p.suggestion) return;
    const s = p.suggestion;
    setMsg(null);
    startTransition(async () => {
      const res = await savePick({ date: p.date, playerId: s.playerId, gameId: s.gameId });
      setMsg(res.ok ? "Réservé. Pense à le reporter sur trashtalk.co." : res.error);
    });
  };

  return (
    <div className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-3 py-2.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-[color:var(--color-text)] capitalize">
          {p.isToday ? "Ce soir" : frLongDate(p.date)}
        </span>
        <span className="text-[10px] text-[color:var(--color-text-mute)]">
          {p.nGames} match{p.nGames > 1 ? "s" : ""} · fermeture {parisTime(p.closingAt)}
        </span>
      </div>
      {p.isPhantom && (
        <p className="mt-1 text-xs text-[color:var(--color-crimson)]">Soirée fantôme : aucun match réel, déplace ta réservation.</p>
      )}
      {p.pick ? (
        <div className="mt-1 text-sm">
          <Link href={`/player/${p.pick.playerId}`} className="font-semibold text-[color:var(--color-emerald)]">
            {p.pick.name}
          </Link>{" "}
          <span className="text-[11px] text-[color:var(--color-text-mute)]">{p.pick.team}{p.pick.isX2 ? " · x2" : ""}</span>
          {p.pick.injury && HARD_OUT.has(p.pick.injury) && (
            <p className="text-xs text-[color:var(--color-crimson)]">⚠️ {p.pick.injury} : remplace-le avant la fermeture.</p>
          )}
        </div>
      ) : p.suggestion ? (
        <div className="mt-1 flex items-center justify-between gap-3">
          <div className="min-w-0 text-sm">
            <Link href={`/player/${p.suggestion.playerId}`} className="text-[color:var(--color-text)]">
              {p.suggestion.name}
            </Link>{" "}
            <span className="text-[11px] text-[color:var(--color-text-mute)]">{p.suggestion.explanation}</span>
          </div>
          <button onClick={reserve} disabled={pending}
                  className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
            RÉSERVER
          </button>
        </div>
      ) : (
        <p className="mt-1 text-xs text-[color:var(--color-text-mute)]">Pas encore de suggestion.</p>
      )}
      {msg && <p role="alert" className="mt-1 text-xs text-[color:var(--color-text-soft)]">{msg}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Implémenter la page**

`web/src/app/deck/page.tsx` :

```tsx
import { supabase } from "@/lib/supabase/public";
import { addDays, deckDate } from "@/lib/date";
import { Night, Player } from "@/types";
import DeckNight from "@/components/DeckNight";

export const revalidate = 0;

type PlanRow = { night: string; player_id: number; projection: number; explanation: string };
type PickRow = { date: string; player_id: number; is_x2: boolean; game_id: string };

export default async function DeckPage() {
  const today = deckDate();
  const until = addDays(today, 14);
  const [nightsRes, planRes, picksRes] = await Promise.all([
    supabase.from("nights").select("*").gte("date", today).lte("date", until).order("date"),
    supabase.from("plan_latest").select("night, player_id, projection, explanation").gte("night", today).lte("night", until),
    supabase.from("picks").select("date, player_id, is_x2, game_id").gte("date", today).lte("date", until),
  ]);
  const nights = (nightsRes.data || []) as Night[];
  const plan = (planRes.data || []) as PlanRow[];
  const picks = (picksRes.data || []) as PickRow[];
  const ids = [...new Set([...plan.map((p) => p.player_id), ...picks.map((p) => p.player_id)])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [] };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  // Match de l'équipe du joueur suggéré, pour réserver en un clic.
  const gamesRes = await supabase.from("games").select("id, date, home_team, away_team").gte("date", today).lte("date", until);
  const games = (gamesRes.data || []) as { id: string; date: string; home_team: string; away_team: string }[];

  return (
    <div className="px-4 py-5 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        DE<span className="flame-text">CK</span>
      </h1>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1 uppercase tracking-[0.18em]">
        14 prochaines soirées · suggestions du plan (indicatives)
      </p>
      <div className="mt-4 flex flex-col gap-2">
        {nights.map((n) => {
          const pick = picks.find((p) => p.date === n.date);
          const pickPlayer = pick ? players.get(pick.player_id) : undefined;
          const s = plan.find((p) => p.night === n.date);
          const sPlayer = s ? players.get(s.player_id) : undefined;
          const sGame = sPlayer ? games.find((g) => g.date === n.date && (g.home_team === sPlayer.team || g.away_team === sPlayer.team)) : undefined;
          return (
            <DeckNight key={n.date} date={n.date} closingAt={n.closing_at} nGames={n.n_eligible_games}
              isPhantom={n.is_phantom} isToday={n.date === today}
              pick={pick && pickPlayer ? { playerId: pickPlayer.id, name: pickPlayer.name, team: pickPlayer.team, injury: pickPlayer.injury_status, isX2: pick.is_x2 } : null}
              suggestion={s && sPlayer && sGame ? { playerId: sPlayer.id, name: sPlayer.name, team: sPlayer.team, gameId: sGame.id, projection: s.projection, explanation: s.explanation } : null} />
          );
        })}
        {nights.length === 0 && <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL dans les 14 prochains jours.</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Vérifier**

Run: `cd web && npm run lint && npx tsc --noEmit && npm test && NEXT_PUBLIC_SUPABASE_URL=http://localhost NEXT_PUBLIC_SUPABASE_ANON_KEY=test npm run build`
Expected: tout passe ; `/deck` apparaît dans la sortie du build.

- [ ] **Step 4: Commiter**

```bash
git add web/src/app/deck web/src/components/DeckNight.tsx
git commit -m "feat(web): deck 14 jours — réservations, suggestions du plan, alertes"
```

---

### Task 11: Matchups de la saison sur les cartes de reco

**Files:**
- Modify: `web/src/app/page.tsx`, `web/src/components/RecommendationCard.tsx`, `web/src/types/index.ts`, `web/src/lib/display.ts`, `web/src/lib/display.test.ts`

**Interfaces:**
- Consumes: vue `matchup_season` (tâche 2).
- Produces:
  - `topDefender(rows: MatchupSeasonRow[]) -> { name: string; share: number; per36: number | null; games: number } | null` (sans échantillon ≥ 5 minutes → `null`) ;
  - `RecommendationWithPlayer.defender?`.

- [ ] **Step 1: Écrire le test**

Ajouter à `web/src/lib/display.test.ts` :

```ts
import { topDefender } from "./display";

describe("topDefender", () => {
  it("prend le défenseur le plus présent et sa part", () => {
    expect(topDefender([
      { def_player_name: "Davis", minutes: 10, points: 12, games: 1 },
      { def_player_name: "James", minutes: 5, points: 5, games: 1 },
    ])).toEqual({ name: "Davis", share: 67, per36: 43.2, games: 1 });
  });
  it("rien sous 5 minutes d'échantillon", () => {
    expect(topDefender([{ def_player_name: "Davis", minutes: 4, points: 3, games: 1 }])).toBeNull();
    expect(topDefender([])).toBeNull();
  });
});
```

- [ ] **Step 2: Implémenter**

Dans `web/src/types/index.ts` :

```ts
export interface MatchupSeasonRow { def_player_name: string | null; minutes: number; points: number; games: number }
```

et ajouter `defender?: { name: string; share: number; per36: number | null; games: number } | null;` à `RecommendationWithPlayer`.

Dans `web/src/lib/display.ts` :

```ts
import type { MatchupSeasonRow } from "@/types";

export function topDefender(rows: MatchupSeasonRow[]) {
  const total = rows.reduce((s, r) => s + r.minutes, 0);
  const top = [...rows].sort((a, b) => b.minutes - a.minutes)[0];
  if (!top || top.minutes < 5 || !top.def_player_name) return null;
  return {
    name: top.def_player_name,
    share: Math.round((top.minutes / total) * 100),
    per36: top.minutes > 0 ? Math.round((top.points / top.minutes) * 36 * 10) / 10 : null,
    games: top.games,
  };
}
```

Dans `web/src/app/page.tsx`, après le calcul de `recsWithPlayers`, charger les matchups de la saison de la soirée pour les joueurs recommandés :

```tsx
const season = night?.season;
let defenders = new Map<string, ReturnType<typeof topDefender>>();
if (season && recsWithPlayers.length) {
  const { data } = await supabase.from("matchup_season")
    .select("player_id, opponent_team, def_player_name, minutes, points, games")
    .eq("season", season).in("player_id", recsWithPlayers.map((r) => r.player_id));
  const byKey = new Map<string, MatchupSeasonRow[]>();
  for (const r of (data || []) as (MatchupSeasonRow & { player_id: number; opponent_team: string })[]) {
    const k = `${r.player_id}:${r.opponent_team}`;
    byKey.set(k, [...(byKey.get(k) ?? []), r]);
  }
  defenders = new Map([...byKey].map(([k, rows]) => [k, topDefender(rows)]));
}
```

puis attacher `defender: defenders.get(`${r.player_id}:${opponent}`) ?? null` à chaque reco (l'adversaire est `game.home_team === player.team ? game.away_team : game.home_team`). Déplacer ce calcul dans `getData` pour garder la page lisible.

Dans `RecommendationCard.tsx`, sous les lignes S1 :

```tsx
{rec.defender && (
  <p className="mt-1 text-[11px] text-[color:var(--color-text-mute)]">
    Défendu par <span className="font-semibold text-[color:var(--color-text)]">{rec.defender.name}</span> ({rec.defender.share} %)
    {rec.defender.per36 !== null && <> · {rec.defender.per36} pts/36 contre lui</>} cette saison
  </p>
)}
```

- [ ] **Step 3: Vérifier**

Run: `cd web && npm test && npx tsc --noEmit && npm run lint && NEXT_PUBLIC_SUPABASE_URL=http://localhost NEXT_PUBLIC_SUPABASE_ANON_KEY=test npm run build`
Expected: PASS.

- [ ] **Step 4: Commiter**

```bash
git add web/src
git commit -m "feat(web): défenseur principal de la saison sur les cartes de reco"
```

---

### Task 12: Mise en prod (contrôleur + utilisateur)

**Files:**
- Modify: `docs/reactivation-saison.md`

- [ ] **Step 1: Mettre à jour la checklist**

Dans `docs/reactivation-saison.md`, section « Quelques jours avant le premier match (après L1c) », ajouter en tête cet ordre :
1. prérequis manuels d'authentification (voir le plan L1c) ;
2. `supabase db push` de la **021** (ajouts) ;
3. déploiement du front (`cd web && npx vercel --prod`), puis connexion par code sur le téléphone ;
4. `supabase db push` de la **022** (fin des écritures anon), seulement après avoir vérifié qu'un pick passe par le nouveau front.

Commiter : `git commit -am "docs: ordre de mise en prod L1c"`.

- [ ] **Step 2: Vérifier les x2 existants (lecture seule)**

```bash
supabase db query --linked "select season, extract(year from date) y, extract(month from date) m, count(*) from picks where is_x2 group by 1,2,3 having count(*) > 1"
```

Expected: aucune ligne. Sinon, l'index `picks_x2_month` échouerait : rapporter et s'arrêter.

- [ ] **Step 3: Feu vert et exécution (utilisateur)**

Présenter à l'utilisateur les prérequis manuels (bloc en tête du plan), puis attendre son « oui » explicite pour chacune de ces étapes :
- `db push` 021 ;
- déploiement Vercel ;
- test de connexion et d'un pick sur le téléphone ;
- `db push` 022.
