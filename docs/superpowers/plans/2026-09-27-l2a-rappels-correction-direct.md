# L2a — fermeture en base, correction, direct ESPN, rappels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Avant le 1er match (2026-10-20) : la base refuse toute modification de pick après la fermeture sauf en mode correction, l'utilisateur corrige ses soirées passées depuis la page Picks, le direct et les statuts de match passent de cdn.nba.com (403) à ESPN, et l'app envoie les rappels (oubli à −2 h/−30 min, alerte blessure) en Web Push, Telegram en secours.

**Architecture:** SQL : un trigger de fermeture séparé de `picks_validate` et une fonction `correct_pick` (drapeau de transaction `ttfl.correction`). Python : `engine/io/espn.py` gagne le scoreboard ESPN ; `daily_sync` n'appelle plus le CDN et tourne aussi toutes les heures le soir (c'est l'`evening_refresh` de la spec, sans nouveau job) ; `local_nightly` score les picks juste après LeagueGameLog. Front : un service worker écrit à la main (le plugin `@ducanh2912/next-pwa` ne génère rien sous Turbopack : `/sw.js` renvoie 404 en prod), abonnement Web Push, route `/api/reminders` appelée par `pg_cron` toutes les 15 min, qui calcule les rappels dus avec une fonction pure testée.

**Tech Stack:** Postgres (Supabase, pg_cron, pg_net, Vault), Python 3.14 (httpx, pytest), Next.js 16.2.3 (App Router, Node 22), `web-push`, vitest.

**Spec:** `docs/superpowers/specs/2026-09-27-l2-design.md` (§3), qui complète `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md`. Règles : `docs/regles-ttfl.md` (R3 cooldown, R8 fermeture, R14 moyenne).

## Global Constraints

- Front : Node 22 pour toute commande (`export PATH=/home/isow/.nvm/versions/node/v22.23.3/bin:$PATH`), lire le guide concerné dans `web/node_modules/next/dist/docs/` avant d'écrire du code Next (Next 16 a des ruptures ; `web/AGENTS.md`).
- Python : `./venv/bin/python -m pytest` depuis la racine. Tests SQL : Postgres jetable local, `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres` (conteneur `ttfl-pg`, voir `docs/operations.md`).
- **Jamais** d'écriture en prod, de `supabase db push`, de déploiement Vercel ou de push git dans les tâches 1 à 9 : seule la tâche 10 (mise en prod) le fait, avec le feu vert de l'utilisateur. Le `.env` racine et `web/.env.local` pointent la prod : ne pas lancer les jobs ni `npm run dev` avec des clics d'écriture.
- Secrets (clés VAPID, `REMINDERS_SECRET`, token Telegram) : jamais affichés, jamais dans le chat ni dans git ; variables d'environnement Vercel / `web/.env.local` / Vault Supabase.
- Toute écriture passe par une action serveur ou une route qui vérifie l'autorisation (`requireOwner()` pour les actions, secret partagé pour `/api/reminders`). La clé service ne quitte jamais le serveur (`import "server-only"`).
- Aucune règle TTFL recalculée en TS sauf miroirs d'affichage commentés (« Miroir de … »).
- Textes de l'interface en français, tutoiement, comme l'existant.
- Commits : message en français au format du dépôt, terminé par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Joueur transféré depuis la soirée corrigée** : `correct_pick` et `picks_validate` doivent retrouver son équipe *de ce soir-là* (`game_logs.team`), pas son équipe actuelle — sinon une correction légitime échoue en `player_not_in_game`. Test SQL tâche 1.
2. **Match ESPN reporté ou annulé** (`STATUS_POSTPONED`, `STATUS_CANCELED`) : ne jamais le marquer `final` ni lui écrire un score. Test Python tâche 3.
3. **Cron qui glisse ou saute un passage** : à −25 min, seul le rappel −30 min part (pas les deux) ; après la fermeture, rien ; soirée sans ligne `nights`, rien ; deux appels simultanés n'envoient qu'une fois (unicité `reminders_sent`). Tests vitest tâche 8.
4. **Abonnement push expiré** (404/410) : supprimé, pas d'exception ; si aucun envoi push n'a réussi et que Telegram est configuré, envoi Telegram. Test vitest tâche 7.
5. **Correction d'une soirée sans ligne `nights`** (avant le 20/10, saison 2025-26) : message clair « soirée inconnue », rien d'écrit. Test SQL tâche 1 + message dans `pickErrorMessage` tâche 5.

---

### Task 1: Migration 023 — fermeture en base et `correct_pick`

**Files:**
- Create: `supabase/migrations/023_closing_correction.sql`
- Test: `tests/sql/test_023_closing_correction.py`

**Interfaces:**
- Consumes: tables `picks`, `nights`, `games`, `game_logs`, `players` ; fonction `player_available_on` (018).
- Produces:
  - trigger `picks_closing_guard` : `P0001 night_closed` sur insert/delete, et sur update de `player_id`, `date`, `game_id` ou `is_x2`, si `now() >= nights.closing_at` d'une des dates concernées ; ignoré quand `current_setting('ttfl.correction', true) = 'on'`.
  - `picks_validate` redéfini : l'équipe du joueur est `game_logs.team` pour ce match si elle existe, sinon `players.team`.
  - `correct_pick(p_date date, p_player_id int) returns void` (`p_player_id` null = suppression) ; `P0001 night_unknown` si pas de soirée éligible à cette date ; `execute` réservé à `service_role`.

- [ ] **Step 1: Écrire les tests SQL**

`tests/sql/test_023_closing_correction.py` :

```python
import psycopg
import pytest


def _seed(pg):
    pg.execute(
        "insert into players (id, name, team, position) values "
        "(1, 'Jokic', 'DEN', 'C'), (2, 'Murray', 'DEN', 'G'), (3, 'Harden', 'LAC', 'G')"
    )
    # Soirée fermée (hier) et soirée ouverte (demain), relatives à now().
    pg.execute(
        "insert into games (id, date, home_team, away_team, game_type, season) values "
        "('0022600010', current_date - 1, 'DEN', 'LAC', 'regular', '2026-27'), "
        "('0022600020', current_date + 1, 'DEN', 'BOS', 'regular', '2026-27')"
    )
    pg.execute(
        "insert into nights (date, season, mode, n_eligible_games, closing_at) values "
        "(current_date - 1, '2026-27', 'regular', 1, now() - interval '1 hour'), "
        "(current_date + 1, '2026-27', 'regular', 1, now() + interval '1 day')"
    )


def test_insert_refuse_apres_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600010', current_date - 1)")


def test_insert_accepte_avant_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600020', current_date + 1)")


def _pick_ferme(pg):
    pg.execute("select set_config('ttfl.correction', 'on', true)")
    pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600010', current_date - 1)")
    pg.execute("select set_config('ttfl.correction', 'off', true)")


def test_score_jamais_bloque(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        _pick_ferme(pg)
        pg.execute("update picks set actual_score = 42 where date = current_date - 1")
        assert pg.execute("select actual_score from picks where date = current_date - 1").fetchone() == (42,)


def test_changement_de_joueur_et_suppression_refuses_apres_fermeture(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        _pick_ferme(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("update picks set player_id = 2 where date = current_date - 1")
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("update picks set is_x2 = true where date = current_date - 1")
        with pytest.raises(psycopg.errors.RaiseException, match="night_closed"):
            with pg.transaction():
                pg.execute("delete from picks where date = current_date - 1")


def test_correct_pick_ajoute_remplace_supprime(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("select correct_pick(current_date - 1, 1)")
        assert pg.execute("select player_id, game_id from picks where date = current_date - 1").fetchone() == (1, "0022600010")
        pg.execute("update picks set actual_score = 30 where date = current_date - 1")
        pg.execute("select correct_pick(current_date - 1, 2)")
        assert pg.execute("select player_id, actual_score from picks where date = current_date - 1").fetchone() == (2, None)
        pg.execute("select correct_pick(current_date - 1, null)")
        assert pg.execute("select count(*) from picks where date = current_date - 1").fetchone() == (0,)


def test_correct_pick_respecte_le_cooldown(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute("insert into picks (player_id, game_id, date) values (1, '0022600020', current_date + 1)")
        with pytest.raises(psycopg.errors.RaiseException, match="player_unavailable:cooldown"):
            with pg.transaction():
                pg.execute("select correct_pick(current_date - 1, 1)")


def test_correct_pick_soiree_inconnue(pg):
    with pg.transaction(force_rollback=True):
        _seed(pg)
        with pytest.raises(psycopg.errors.RaiseException, match="night_unknown"):
            with pg.transaction():
                pg.execute("select correct_pick(current_date - 30, 1)")


def test_correct_pick_joueur_transfere_depuis(pg):
    """Harden jouait pour DEN ce soir-là (game_logs), il est à LAC aujourd'hui."""
    with pg.transaction(force_rollback=True):
        _seed(pg)
        pg.execute(
            "insert into game_logs (player_id, game_id, date, team, pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, "
            "ftm, fta, tov, minutes, ttfl_score, is_home, season) values "
            "(3, '0022600010', current_date - 1, 'DEN', 20, 5, 5, 1, 0, 8, 15, 2, 5, 2, 2, 3, 34, 25, true, '2026-27')"
        )
        pg.execute("update players set team = 'BOS' where id = 3")
        pg.execute("select correct_pick(current_date - 1, 3)")
        assert pg.execute("select player_id from picks where date = current_date - 1").fetchone() == (3,)


def test_correct_pick_interdit_a_anon(pg):
    with pg.transaction(force_rollback=True):
        grants = pg.execute(
            "select has_function_privilege('anon', 'correct_pick(date, integer)', 'execute')"
        ).fetchone()
        assert grants == (False,)
```

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql/test_023_closing_correction.py -q`
Expected: FAIL (`night_closed` jamais levée, `correct_pick` inexistante). Si le conteneur n'existe pas : `docker run -d --name ttfl-pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:17` (ou `docker start ttfl-pg`). Vérifier dans `tests/sql/conftest.py` que les rôles `anon`/`service_role` existent dans la base jetable ; s'ils n'existent pas, les créer dans le conftest (`create role anon nologin` si absent) comme le font déjà les tests de 022.

- [ ] **Step 3: Écrire la migration**

`supabase/migrations/023_closing_correction.sql` :

```sql
-- 023 — Fermeture du deck en base (R8) et mode correction (spec L2 §3.1).

-- Équipe du joueur pour un match : celle de son log si le match est joué
-- (joueur transféré depuis), sinon son équipe actuelle.
create or replace function player_team_for_game(p_player_id int, p_game_id text)
returns text language sql stable as $$
  select coalesce(
    (select l.team from game_logs l where l.player_id = p_player_id and l.game_id = p_game_id limit 1),
    (select team from players where id = p_player_id))
$$;

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
  if coalesce(g.game_type, 'unknown') not in ('regular', 'cup_final', 'playoffs') then
    raise exception 'night_not_eligible:%', coalesce(g.game_type, 'unknown') using errcode = 'P0001';
  end if;
  if g.date <> new.date then
    raise exception 'date_mismatch' using errcode = 'P0001';
  end if;
  v_team := player_team_for_game(new.player_id, new.game_id);
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

-- R8 : plus aucun changement de pick une fois la soirée fermée, sauf en
-- mode correction. Les écritures de score (actual_score) passent toujours.
create or replace function picks_closing_guard() returns trigger
language plpgsql as $$
declare
  v_dates date[];
begin
  if current_setting('ttfl.correction', true) = 'on' then
    return coalesce(new, old);
  end if;
  if tg_op = 'INSERT' then
    v_dates := array[new.date];
  elsif tg_op = 'DELETE' then
    v_dates := array[old.date];
  else
    if new.player_id is not distinct from old.player_id
       and new.date is not distinct from old.date
       and new.game_id is not distinct from old.game_id
       and new.is_x2 is not distinct from old.is_x2 then
      return new;
    end if;
    v_dates := array[old.date, new.date];
  end if;
  if exists (select 1 from nights n where n.date = any(v_dates) and now() >= n.closing_at) then
    raise exception 'night_closed' using errcode = 'P0001';
  end if;
  return coalesce(new, old);
end
$$;
drop trigger if exists picks_closing_guard on picks;
create trigger picks_closing_guard before insert or update or delete on picks
  for each row execute function picks_closing_guard();

-- Correction d'une soirée passée (synchro manuelle TrashTalk oubliée).
-- Lève la fermeture pour cette transaction seulement ; cooldown, éligibilité
-- et unicité restent vérifiés par picks_validate et les contraintes.
create or replace function correct_pick(p_date date, p_player_id int) returns void
language plpgsql security definer set search_path = public as $$
declare
  v_game text;
begin
  perform set_config('ttfl.correction', 'on', true);
  if not exists (select 1 from nights n where n.date = p_date and not n.is_phantom and n.n_eligible_games > 0) then
    raise exception 'night_unknown' using errcode = 'P0001';
  end if;
  if p_player_id is null then
    delete from picks where date = p_date;
    return;
  end if;
  select g.id into v_game from games g
  where g.date = p_date and g.game_type in ('regular', 'cup_final', 'playoffs')
    and player_team_for_game(p_player_id, g.id) in (g.home_team, g.away_team)
  limit 1;
  if v_game is null then
    raise exception 'player_not_in_game' using errcode = 'P0001';
  end if;
  if exists (select 1 from picks where date = p_date) then
    update picks set player_id = p_player_id, game_id = v_game, actual_score = null where date = p_date;
  else
    insert into picks (player_id, game_id, date) values (p_player_id, v_game, p_date);
  end if;
end
$$;
revoke execute on function correct_pick(date, int) from public;
revoke execute on function correct_pick(date, int) from anon, authenticated;
grant execute on function correct_pick(date, int) to service_role;
```

Note pour l'implémenteur : `player_team_for_game` avec `game_logs.team` null (vieux logs) retombe sur `players.team` grâce au `coalesce` — vérifier que `game_logs.team` peut être null (017) et que le `limit 1` d'une sous-requête scalaire est bien accepté.

- [ ] **Step 4: Vérifier que les tests passent, et toute la suite SQL**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -q`
Expected: tout PASS (y compris 018 : la redéfinition de `picks_validate` ne doit rien casser).

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/023_closing_correction.sql tests/sql/test_023_closing_correction.py
git commit -m "feat(db): fermeture du deck en base (R8) et correction des soirées passées (023)"
```

---

### Task 2: Migration 024 — tables des rappels, et SQL manuel du cron

**Files:**
- Create: `supabase/migrations/024_reminders.sql`, `supabase/manual/reminders_cron.sql`
- Test: `tests/sql/test_024_reminders.py`

**Interfaces:**
- Produces: tables `push_subscriptions(id, endpoint unique, p256dh, auth, created_at, last_ok_at)` et `reminders_sent(id, night date, kind text, key text, sent_at, unique(night, kind, key))`, RLS activé sans aucune policy (seule la clé service y accède). `supabase/manual/reminders_cron.sql` : planification `pg_cron` appliquée à la main en prod (tâche 10) — hors migrations parce que `pg_cron`/`pg_net`/Vault n'existent pas dans la Postgres jetable des tests.

- [ ] **Step 1: Tests**

`tests/sql/test_024_reminders.py` :

```python
import psycopg
import pytest


def test_reminders_sent_unique(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into reminders_sent (night, kind, key) values ('2026-10-21', 'no_pick_2h', '')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg.transaction():
                pg.execute("insert into reminders_sent (night, kind, key) values ('2026-10-21', 'no_pick_2h', '')")


def test_push_subscriptions_endpoint_unique(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into push_subscriptions (endpoint, p256dh, auth) values ('https://x/1', 'k', 'a')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg.transaction():
                pg.execute("insert into push_subscriptions (endpoint, p256dh, auth) values ('https://x/1', 'k', 'a')")


def test_rls_sans_policy(pg):
    rows = pg.execute(
        "select tablename from pg_policies where tablename in ('push_subscriptions', 'reminders_sent')"
    ).fetchall()
    assert rows == []
    enabled = pg.execute(
        "select relname, relrowsecurity from pg_class where relname in ('push_subscriptions', 'reminders_sent') order by relname"
    ).fetchall()
    assert enabled == [("push_subscriptions", True), ("reminders_sent", True)]
```

- [ ] **Step 2: Vérifier l'échec**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql/test_024_reminders.py -q`
Expected: FAIL (tables absentes).

- [ ] **Step 3: Migration et SQL manuel**

`supabase/migrations/024_reminders.sql` :

```sql
-- 024 — Rappels (spec L2 §3.4). Accès par la clé service uniquement.
create table if not exists push_subscriptions (
  id bigserial primary key,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now(),
  last_ok_at timestamptz
);
alter table push_subscriptions enable row level security;

create table if not exists reminders_sent (
  id bigserial primary key,
  night date not null,
  kind text not null,
  key text not null default '',
  sent_at timestamptz not null default now(),
  unique (night, kind, key)
);
alter table reminders_sent enable row level security;
```

`supabase/manual/reminders_cron.sql` :

```sql
-- À exécuter UNE fois en prod (tâche 10 du plan L2a), après avoir créé le
-- secret dans Vault :  select vault.create_secret('<valeur>', 'reminders_secret');
-- (valeur = REMINDERS_SECRET de Vercel ; ne jamais la committer).
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.unschedule('ttfl-reminders')
where exists (select 1 from cron.job where jobname = 'ttfl-reminders');

select cron.schedule('ttfl-reminders', '*/15 * * * *', $$
  select net.http_post(
    url := 'https://ttfl-advisor.vercel.app/api/reminders',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'reminders_secret')
    ),
    body := '{}'::jsonb
  )
$$);
```

- [ ] **Step 4: Tests SQL complets**

Run: `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/024_reminders.sql supabase/manual/reminders_cron.sql tests/sql/test_024_reminders.py
git commit -m "feat(db): tables des rappels (024) et planification pg_cron manuelle"
```

---

### Task 3: Scoreboard ESPN côté moteur

**Files:**
- Modify: `engine/io/espn.py`
- Test: `tests/io/test_espn.py`

**Interfaces:**
- Produces:
  - `ESPN_ABBR_TO_TRICODE: dict[str, str]` et `espn_tricode(abbr: str) -> str` ;
  - `parse_espn_scoreboard(payload: dict, game_date: date) -> list[dict]` : lignes `{"date", "home_team", "away_team", "tip_off", "status", "home_score", "away_score"}` (sans `id` : l'appariement avec `games` est fait par le job) ; matchs reportés/annulés exclus ;
  - `fetch_espn_scoreboard(game_date: date, guard=None) -> list[dict]` (1 appel, `guard.call("espn", ...)` si guard fourni).

- [ ] **Step 1: Tests**

Ajouter à `tests/io/test_espn.py` :

```python
from datetime import date

from engine.io.espn import espn_tricode, parse_espn_scoreboard


def _event(state, name, home="GS", away="NY", hs="100", as_="98", when="2026-10-22T02:00Z"):
    return {
        "date": when,
        "status": {"type": {"state": state, "name": name}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": home}, "score": hs},
            {"homeAway": "away", "team": {"abbreviation": away}, "score": as_},
        ]}],
    }


def test_tricodes_espn_normalises():
    assert [espn_tricode(a) for a in ["GS", "NY", "SA", "NO", "UTAH", "WSH", "BOS"]] == \
        ["GSW", "NYK", "SAS", "NOP", "UTA", "WAS", "BOS"]


def test_scoreboard_statuts_et_scores():
    payload = {"events": [_event("post", "STATUS_FINAL"), _event("in", "STATUS_IN_PROGRESS", home="SA", away="UTAH"),
                          _event("pre", "STATUS_SCHEDULED", home="LAL", away="WSH", hs="0", as_="0")]}
    rows = parse_espn_scoreboard(payload, date(2026, 10, 21))
    assert rows[0] == {"date": "2026-10-21", "home_team": "GSW", "away_team": "NYK", "tip_off": "2026-10-22T02:00Z",
                       "status": "final", "home_score": 100, "away_score": 98}
    assert (rows[1]["home_team"], rows[1]["away_team"], rows[1]["status"]) == ("SAS", "UTA", "live")
    assert rows[2]["status"] == "scheduled" and rows[2]["home_score"] is None


def test_scoreboard_ignore_reportes_et_annules():
    payload = {"events": [_event("post", "STATUS_POSTPONED"), _event("post", "STATUS_CANCELED")]}
    assert parse_espn_scoreboard(payload, date(2026, 10, 21)) == []
```

- [ ] **Step 2: Vérifier l'échec** — Run: `./venv/bin/python -m pytest tests/io/test_espn.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implémenter** (dans `engine/io/espn.py`, après les dictionnaires d'équipes)

```python
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# Abréviations ESPN qui diffèrent des tricodes NBA de la table games.
ESPN_ABBR_TO_TRICODE = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}
_SKIPPED_STATUSES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED"}


def espn_tricode(abbr: str) -> str:
    return ESPN_ABBR_TO_TRICODE.get(abbr, abbr)


def parse_espn_scoreboard(payload: dict, game_date: date) -> list[dict]:
    """Statuts et scores des matchs d'une journée NBA (date US). Les matchs
    reportés ou annulés sont exclus : jamais marqués final."""
    rows = []
    for ev in payload.get("events", []):
        status_type = ev.get("status", {}).get("type", {})
        if status_type.get("name") in _SKIPPED_STATUSES:
            continue
        status = {"post": "final", "in": "live"}.get(status_type.get("state"), "scheduled")
        teams = {c["homeAway"]: c for c in ev["competitions"][0]["competitors"]}
        played = status != "scheduled"
        rows.append({
            "date": game_date.isoformat(),
            "home_team": espn_tricode(teams["home"]["team"]["abbreviation"]),
            "away_team": espn_tricode(teams["away"]["team"]["abbreviation"]),
            "tip_off": ev.get("date"),
            "status": status,
            "home_score": int(teams["home"].get("score") or 0) if played else None,
            "away_score": int(teams["away"].get("score") or 0) if played else None,
        })
    return rows


def fetch_espn_scoreboard(game_date: date, guard=None) -> list[dict]:
    def download():
        resp = httpx.get(SCOREBOARD_URL, params={"dates": game_date.strftime("%Y%m%d")}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    payload = guard.call("espn", download) if guard is not None else download()
    return parse_espn_scoreboard(payload, game_date)
```

(Ajouter `from datetime import date` en tête du module.)

- [ ] **Step 4: Tests** — Run: `./venv/bin/python -m pytest tests/io -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/io/espn.py tests/io/test_espn.py
git commit -m "feat(io): scoreboard ESPN (statuts et scores, reportés exclus)"
```

---

### Task 4: `daily_sync` sans CDN, scoring des picks par `local_nightly`, passages du soir

**Files:**
- Modify: `engine/jobs/daily_sync.py`, `engine/jobs/local_nightly.py`, `.github/workflows/daily-sync.yml`, `tests/jobs/test_daily_sync.py`, `tests/jobs/test_local_nightly.py`, `tests/jobs/fakes.py`

**Interfaces:**
- Consumes: `fetch_espn_scoreboard(game_date, guard)` (tâche 3).
- Produces:
  - `run(repo, fetch_scoreboard, fetch_injuries, today, now) -> RunResult` : `fetch_scoreboard(d: date) -> list[dict]` (lignes de `parse_espn_scoreboard`) ; plus d'argument `source`, plus d'appel CDN (calendrier et box scores : `local_nightly` s'en charge).
  - `score_picks(repo, season, today)` (ex-`_score_picks`, rendu public, inchangé), appelé aussi par `local_nightly.run` après le chargement des logs.
  - `apply_scoreboard(repo, rows, window_games) -> int` : met à jour `status`, `home_score`, `away_score`, `tip_off` des matchs de `games` appariés par (date, domicile, extérieur) ; renvoie le nombre de matchs mis à jour ; une ligne sans match correspondant est ignorée.

- [ ] **Step 1: Tests**

Dans `tests/jobs/test_daily_sync.py`, remplacer les usages de `FakeNbaSource` par une fonction `fetch_scoreboard` factice et ajouter :

```python
def test_scoreboard_espn_apparie_par_date_et_equipes():
    game = {"id": "0022600001", "date": "2026-10-20", "home_team": "DET", "away_team": "BOS",
            "status": "scheduled", "game_type": "regular", "season": "2026-27"}
    repo = FakeRepo(games=[game])
    rows = [{"date": "2026-10-20", "home_team": "DET", "away_team": "BOS", "tip_off": "2026-10-20T19:00Z",
             "status": "final", "home_score": 101, "away_score": 99},
            {"date": "2026-10-20", "home_team": "XXX", "away_team": "YYY", "tip_off": None,
             "status": "final", "home_score": 1, "away_score": 2}]
    assert apply_scoreboard(repo, rows, [game]) == 1
    stored = repo.games["0022600001"]
    assert (stored["status"], stored["home_score"], stored["away_score"]) == ("final", 101, 99)


def test_daily_sync_n_appelle_plus_le_cdn():
    calls = []
    run(FakeRepo(), lambda d: calls.append(d) or [], lambda: {}, TODAY, NOW)
    assert calls == [TODAY - timedelta(days=1), TODAY]   # journée US d'hier et d'aujourd'hui
```

Dans `tests/jobs/test_local_nightly.py` :

```python
def test_picks_scores_des_le_chargement_des_logs():
    # Un pick d'hier, un log LeagueGameLog pour ce match → score posé par local_nightly.
    ...
```
(compléter avec les fixtures existantes du fichier : un joueur, un match d'hier `final`, un pick sans score, un log de 37 → `repo.picks[...]["actual_score"] == 37`.)

Adapter `tests/jobs/fakes.py` : `FakeRepo.upsert_games` doit fusionner les colonnes (pas remplacer la ligne) ; supprimer `FakeNbaSource` s'il n'est plus utilisé.

- [ ] **Step 2: Vérifier l'échec** — Run: `./venv/bin/python -m pytest tests/jobs -q` → FAIL.

- [ ] **Step 3: Implémenter**

Dans `daily_sync.py` :
- supprimer les étapes « calendrier » et « box score » (`_ingest_box_scores`, `source.schedule`, `source.box_score`) ; supprimer les imports devenus inutiles ;
- nouvelle fonction :

```python
def apply_scoreboard(repo, rows: list[dict], window_games: list[dict]) -> int:
    """Statuts/scores ESPN → table games, appariés par (date, domicile, extérieur)."""
    by_key = {(str(g["date"])[:10], g["home_team"], g["away_team"]): g for g in window_games}
    updates = []
    for r in rows:
        g = by_key.get((r["date"], r["home_team"], r["away_team"]))
        if g is None:
            continue
        updates.append({"id": g["id"], "date": g["date"], "home_team": g["home_team"], "away_team": g["away_team"],
                        "status": r["status"], "home_score": r["home_score"], "away_score": r["away_score"],
                        **({"tip_off": r["tip_off"]} if r.get("tip_off") else {})})
    if updates:
        repo.upsert_games(updates)
    return len(updates)
```

- dans `run(repo, fetch_scoreboard, fetch_injuries, today, now)` : au début,

```python
    window_games = repo.load_games_between(today - timedelta(days=1), today)
    for d in (today - timedelta(days=1), today):
        board = _step(f"scoreboard {d}", lambda d=d: fetch_scoreboard(d), result)
        if board:
            apply_scoreboard(repo, board, window_games)
    known = ...  # (inchangé, si encore utilisé ; sinon supprimer)
    score_picks(repo, season, today)
```

- `main()` : `run(repo, lambda d: fetch_espn_scoreboard(d, guard), lambda: fetch_all_injuries(guard), today, now)` ; plus de `NbaSource`.

Dans `local_nightly.py` : après les appels `_load_logs(...)` de la saison courante (hors backfill), appeler `score_picks(repo, season, today)` (import depuis `engine.jobs.daily_sync`). Les matchs LeagueGameLog sont déjà `status: "final"` (`parse_league_game_log`), donc `_is_settled` les accepte.

Dans `.github/workflows/daily-sync.yml`, ajouter les passages du soir (evening_refresh de la spec) et mettre à jour le commentaire :

```yaml
  schedule:
    - cron: "0 5 * * *"      # 07:00 Paris (CEST)
    - cron: "0 10 * * *"     # 12:00 Paris
    - cron: "0 15 * * *"     # 17:00 Paris
    - cron: "0 16-21 * * *"  # 18:00 → 23:00 Paris, toutes les heures (blessures, P(joue), plan)
```

(retirer l'ancienne ligne `0 20 * * *`, couverte par `16-21`).

- [ ] **Step 4: Tests** — Run: `./venv/bin/python -m pytest -q` → PASS (toute la suite Python).

- [ ] **Step 5: Commit**

```bash
git add engine/jobs tests/jobs .github/workflows/daily-sync.yml
git commit -m "feat(jobs): statuts ESPN au lieu du CDN, picks scorés par local_nightly, passages horaires le soir"
```

---

### Task 5: Correction des soirées passées dans la page Picks

**Files:**
- Modify: `web/src/app/actions.ts`, `web/src/lib/errors.ts`, `web/src/lib/errors.test.ts`, `web/src/app/picks/page.tsx`, `web/src/app/picks/PicksHistory.tsx`
- Create: `web/src/app/picks/CorrectionPanel.tsx`

**Interfaces:**
- Consumes: RPC `correct_pick(p_date, p_player_id)` (tâche 1) via `adminClient()` ; `requireOwner()`, `deckDate()`, `seasonForDate()`.
- Produces:
  - `correctPick(input: { date: string; playerId: number | null }): Promise<ActionResult>` ;
  - `playersForNight(date: string): Promise<{ id: number; name: string; team: string }[]>` (joueurs actifs des équipes qui jouent un match éligible ce soir-là ; `requireOwner()` d'abord, liste vide sinon) ;
  - `pickErrorMessage` gère `night_closed` (« La soirée est fermée. ») et `night_unknown` (« Soirée inconnue : elle ne compte pas ou n'est pas encore en base. »).

- [ ] **Step 1: Tests des messages** — ajouter à `web/src/lib/errors.test.ts` :

```ts
it("fermeture et soirée inconnue", () => {
  expect(pickErrorMessage({ code: "P0001", message: "night_closed" })).toBe("La soirée est fermée.");
  expect(pickErrorMessage({ code: "P0001", message: "night_unknown" }))
    .toBe("Soirée inconnue : elle ne compte pas ou n'est pas encore en base.");
});
```

Run: `cd web && npm test` → FAIL ; puis ajouter les deux cas dans `pickErrorMessage` (bloc `P0001`) → PASS.

- [ ] **Step 2: Actions serveur** — dans `web/src/app/actions.ts`, sur le modèle des actions existantes (garde `owner()`, `getAdmin()`, `refresh()`) :

```ts
/** Correction d'une soirée passée de la saison (synchro TrashTalk oubliée) :
 *  lève la fermeture en base (correct_pick), jamais le cooldown. */
export async function correctPick(input: { date: string; playerId: number | null }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const today = deckDate();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.date) || input.date >= today) {
    return { ok: false, error: "Seules les soirées passées se corrigent ici." };
  }
  if (seasonForDate(input.date) !== seasonForDate(today)) {
    return { ok: false, error: "Seules les soirées de la saison en cours se corrigent." };
  }
  const db = getAdmin();
  if (!db.ok) return db.result;
  const { error } = await db.client.rpc("correct_pick", { p_date: input.date, p_player_id: input.playerId });
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh(input.playerId ?? undefined);
  return { ok: true };
}

export async function playersForNight(date: string): Promise<{ id: number; name: string; team: string }[]> {
  if (await owner()) return [];
  const db = getAdmin();
  if (!db.ok) return [];
  const { data: games } = await db.client.from("games").select("home_team, away_team")
    .eq("date", date).in("game_type", ["regular", "cup_final", "playoffs"]);
  const teams = [...new Set((games ?? []).flatMap((g) => [g.home_team, g.away_team]))];
  if (!teams.length) return [];
  const { data } = await db.client.from("players").select("id, name, team")
    .in("team", teams).eq("active", true).order("name");
  return data ?? [];
}
```

(Adapter `getAdmin()` à sa signature réelle dans le fichier — lire `actions.ts` ; si elle renvoie autre chose, garder le même motif que `savePick`.) Limite connue et acceptée : `playersForNight` propose l'effectif actuel ; un joueur transféré depuis se corrige en base à la demande.

- [ ] **Step 3: Données de la page** — dans `web/src/app/picks/page.tsx`, charger aussi les soirées passées de la saison : `nights` (`date, n_eligible_games, is_phantom`) avec `season = saison courante`, `date < today`, `not is_phantom`, `n_eligible_games > 0`, triées décroissantes ; les fusionner avec les picks pour que `PicksHistory` reçoive aussi les soirées **sans pick** (ligne « aucun pick · compte 0 »).

- [ ] **Step 4: Composant** — `web/src/app/picks/CorrectionPanel.tsx` (client) : props `{ date: string; currentPlayerId: number | null; onDone: () => void }`. Au montage, `playersForNight(date)` ; champ de recherche filtrant la liste par nom (insensible aux accents : `normalize("NFD").replace(/\p{Diacritic}/gu, "")`) ; clic sur un joueur → `correctPick({ date, playerId })` ; bouton « Supprimer ce pick » (si `currentPlayerId`) en deux temps : 1er clic → « Confirmer : la soirée comptera 0 », 2e clic → `correctPick({ date, playerId: null })`. `useTransition` pour l'état en cours, erreur affichée dans un `role="alert"`, jamais de succès simulé. Dans `PicksHistory.tsx`, sur chaque soirée passée (avec ou sans pick) un bouton discret « Corriger » ouvre/ferme le panneau pour cette ligne.

- [ ] **Step 5: Vérifier** — Run: `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → tout vert.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/actions.ts web/src/lib/errors.ts web/src/lib/errors.test.ts web/src/app/picks
git commit -m "feat(web): corriger une soirée passée depuis la page Picks (remplacer, ajouter, supprimer)"
```

---

### Task 6: Box score en direct via ESPN

**Files:**
- Create: `web/src/lib/espn.ts`, `web/src/lib/espn.test.ts`
- Modify: `web/src/app/api/live-box-score/[gameId]/route.ts`

**Interfaces:**
- Produces (`web/src/lib/espn.ts`, pur, sans accès réseau sauf `fetchEspnLiveBox`) :
  - `espnTricode(abbr: string): string` (miroir de `engine/io/espn.py`) ;
  - `normalizeName(name: string): string` (miroir de `_normalize` : minuscules, sans accents ni ponctuation, sans suffixes jr/sr/ii/iii/iv) ;
  - `matchPlayerId(name: string, candidates: { id: number; name: string }[]): number | null` (miroir de `match_injury_to_player` : nom exact normalisé, sinon même nom de famille ET même prénom ; `null` si aucun) ;
  - `parseEspnBox(summary: unknown): { team: string; name: string; starter: boolean; played: boolean; minutes: number; pts; reb; ast; stl; blk; fgm; fga; tpm; tpa; ftm; fta; tov; fouls }[]` (labels `MIN, PTS, FG, 3PT, FT, REB, AST, TO, STL, BLK, OREB, DREB, PF, +/-`, lus par leur position dans `labels`, pas par index fixe) ;
  - `findEspnEvent(scoreboard: unknown, home: string, away: string): { id: string; state: string; period: number; clock: string; homeScore: number; awayScore: number } | null`.
- La route garde exactement la forme de réponse actuelle (consommée par `LiveBoxScore.tsx`).

- [ ] **Step 1: Tests** — `web/src/lib/espn.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { espnTricode, findEspnEvent, matchPlayerId, normalizeName, parseEspnBox } from "./espn";

describe("espn", () => {
  it("tricodes", () => {
    expect(["GS", "NY", "SA", "NO", "UTAH", "WSH", "BOS"].map(espnTricode))
      .toEqual(["GSW", "NYK", "SAS", "NOP", "UTA", "WAS", "BOS"]);
  });
  it("normalise les noms", () => {
    expect(normalizeName("Nikola Jokić")).toBe("nikola jokic");
    expect(normalizeName("Jaren Jackson Jr.")).toBe("jaren jackson");
    expect(normalizeName("P.J. Washington")).toBe("pj washington");
  });
  it("apparie sans confondre les homonymes", () => {
    const team = [{ id: 1, name: "Jalen Williams" }, { id: 2, name: "Jaylin Williams" }];
    expect(matchPlayerId("Jaylin Williams", team)).toBe(2);
    expect(matchPlayerId("Kenrich Williams", team)).toBeNull();
  });
  it("lit le box score par libellés", () => {
    const summary = { boxscore: { players: [{ team: { abbreviation: "GS" }, statistics: [{
      labels: ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"],
      athletes: [
        { athlete: { displayName: "Stephen Curry" }, starter: true, didNotPlay: false,
          stats: ["34", "30", "10-20", "5-11", "5-5", "4", "6", "3", "1", "0", "0", "4", "2", "+8"] },
        { athlete: { displayName: "Bench Guy" }, starter: false, didNotPlay: true, stats: [] },
      ] }] }] } };
    const rows = parseEspnBox(summary);
    expect(rows[0]).toMatchObject({ team: "GSW", name: "Stephen Curry", played: true, minutes: 34, pts: 30,
      fgm: 10, fga: 20, tpm: 5, tpa: 11, ftm: 5, fta: 5, reb: 4, ast: 6, tov: 3, stl: 1, blk: 0, fouls: 2 });
    expect(rows[1]).toMatchObject({ played: false, minutes: 0, pts: 0 });
  });
  it("trouve le match par équipes", () => {
    const sb = { events: [{ id: "401", status: { period: 2, displayClock: "5:12", type: { state: "in" } },
      competitions: [{ competitors: [
        { homeAway: "home", team: { abbreviation: "GS" }, score: "50" },
        { homeAway: "away", team: { abbreviation: "NY" }, score: "48" }] }] }] };
    expect(findEspnEvent(sb, "GSW", "NYK")).toEqual({ id: "401", state: "in", period: 2, clock: "5:12", homeScore: 50, awayScore: 48 });
    expect(findEspnEvent(sb, "BOS", "NYK")).toBeNull();
  });
});
```

- [ ] **Step 2: Échec** — Run: `cd web && npm test` → FAIL (module absent).

- [ ] **Step 3: Implémenter `web/src/lib/espn.ts`** (fonctions pures ci-dessus + `fetchEspnLiveBox(date: string, home: string, away: string)` qui appelle `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD` puis `.../summary?event=<id>`, `next: { revalidate: 8 }`, et renvoie `{ event, rows }` ou `null`). En tête du fichier : commentaire « Miroirs de engine/io/espn.py (tricodes, normalisation, appariement) ».

- [ ] **Step 4: Route** — dans `route.ts` : garder la branche `final` → `game_logs` ; remplacer toute la branche cdn.nba.com par : lire `games.date, home_team, away_team` ; `fetchEspnLiveBox(date, home, away)` ; `null` → 502 `{ error: "upstream" }` ; charger les joueurs des deux équipes (`players` : `id, name, team`) et construire chaque ligne avec `player_id: matchPlayerId(name, joueursDeSonEquipe)` (ligne non appariée : `player_id: null`, conservée pour l'affichage mais sans lien), `ttfl_score: computeTtflScore(stats)`, statut `status: state === "post" ? 3 : state === "in" ? 2 : 1`, `status_text`, `period`, `game_clock`. Vérifier dans `LiveBoxScore.tsx` que `player_id: null` ne casse rien (lien désactivé). Supprimer les types `Raw*` et `mapPlayer` devenus inutiles.

- [ ] **Step 5: Vérifier** — Run: `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → vert. Vérification manuelle (lecture seule, autorisée) : `curl -s "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260410" | head -c 200` répond ; ne pas lancer `npm run dev`.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/espn.ts web/src/lib/espn.test.ts "web/src/app/api/live-box-score/[gameId]/route.ts"
git commit -m "feat(web): box score en direct via ESPN (cdn.nba.com renvoie 403)"
```

---

### Task 7: Service worker, abonnement Web Push, notifier

**Files:**
- Create: `web/public/sw.js`, `web/src/lib/notify.ts`, `web/src/lib/notify.test.ts`, `web/src/app/rappels/page.tsx`, `web/src/app/rappels/PushControls.tsx`, `web/src/components/ServiceWorker.tsx`
- Modify: `web/package.json` (ajout `web-push`, `@types/web-push` ; retrait `@ducanh2912/next-pwa`), `web/next.config.ts`, `web/src/app/layout.tsx`, `web/src/app/actions.ts`, `web/src/app/picks/page.tsx` (lien « Rappels » à côté de Déconnexion), `web/.env.local.example`, `web/src/proxy.ts` (exclure `sw.js` s'il ne l'est pas déjà)

**Interfaces:**
- Consumes: table `push_subscriptions` (tâche 2).
- Produces:
  - `notifyAll(msg: { title: string; body: string; url?: string }, deps?): Promise<{ push: number; telegram: boolean }>` (`web/src/lib/notify.ts`, `import "server-only"`) : envoie à tous les abonnements (web-push, VAPID `NEXT_PUBLIC_VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / sujet `mailto:` depuis `OWNER_EMAIL`), supprime les abonnements en 404/410, met `last_ok_at` sur les succès ; si **aucun** envoi push n'a réussi et que `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` sont définis, envoie sur Telegram (`https://api.telegram.org/bot<token>/sendMessage`). `deps` injecte `sendPush`, `sendTelegram`, `db` pour les tests.
  - actions `subscribePush(sub: { endpoint: string; keys: { p256dh: string; auth: string } }): Promise<ActionResult>`, `unsubscribePush(endpoint: string): Promise<ActionResult>`, `sendTestNotification(): Promise<ActionResult>` (toutes derrière `owner()`).
  - page `/rappels`.

- [ ] **Step 1: Lire la doc** — `web/node_modules/next/dist/docs/01-app/02-guides/progressive-web-apps.md` (sections 2 et 3 : `sw.js`, `pushManager.subscribe`, `web-push`), puis la section iOS (PWA installée depuis Safari, iOS ≥ 16.4).

- [ ] **Step 2: Tests du notifier** — `web/src/lib/notify.test.ts` : avec `deps` factices (vitest alias `server-only` déjà géré ? sinon ajouter `resolve.alias: { "server-only": "<fichier vide>" }` dans `vitest.config.mts`) :
  - 2 abonnements, l'un renvoie `{ statusCode: 410 }` → supprimé de la base factice, `push === 1`, Telegram non appelé ;
  - tous les envois échouent, Telegram configuré → `telegram === true` ;
  - aucun abonnement et Telegram non configuré → `{ push: 0, telegram: false }` sans exception.

- [ ] **Step 3: Implémenter** :
  - `npm install web-push && npm install -D @types/web-push && npm uninstall @ducanh2912/next-pwa` ; `next.config.ts` exporte `nextConfig` sans `withPWA` (garder `turbopack: {}`).
  - `web/public/sw.js` : écouteurs `push` (affiche `title`, `body`, `icon: "/icons/icon-192.png"` — vérifier le nom réel dans `public/icons/` —, `data.url`) et `notificationclick` (ferme la notification, focus un onglet existant de l'app ou `clients.openWindow(data.url || "/")`). Pas de cache hors-ligne dans ce lot.
  - `ServiceWorker.tsx` (client, monté dans `layout.tsx`) : `navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" })` si supporté.
  - `PushControls.tsx` : état (non supporté / pas installée / désactivé / activé) ; « Activer les rappels » → `Notification.requestPermission()` puis `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })` → `subscribePush(JSON.parse(JSON.stringify(sub)))` ; « Envoyer une notification de test » → `sendTestNotification()` ; « Désactiver ». Message explicite si iOS hors PWA installée : « Sur iPhone, ajoute d'abord l'app à l'écran d'accueil (Partager → Sur l'écran d'accueil), puis ouvre-la depuis l'icône. »
  - `/rappels/page.tsx` : titre « RAPPELS », explication des deux rappels (oubli −2 h/−30 min, blessure du pick) et `PushControls`.
  - `.env.local.example` : `NEXT_PUBLIC_VAPID_PUBLIC_KEY=`, `VAPID_PRIVATE_KEY=`, `REMINDERS_SECRET=`, `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHAT_ID=` (vides).

- [ ] **Step 4: Vérifier** — Run: `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → vert ; `ls web/public/sw.js` présent ; la sortie du build liste `/rappels`.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): service worker écrit à la main, abonnement Web Push, notifier avec secours Telegram"
```

---

### Task 8: Route `/api/reminders` (oubli et alerte blessure)

**Files:**
- Create: `web/src/lib/reminders.ts`, `web/src/lib/reminders.test.ts`, `web/src/app/api/reminders/route.ts`

**Interfaces:**
- Consumes: `notifyAll` (tâche 7), `HARD_OUT_STATUSES` (`web/src/lib/display.ts`), `deckDate()`, `parisTime()`, tables `nights`, `picks`, `players`, `reminders_sent`.
- Produces:
  - `dueReminders(input: { now: Date; night: { date: string; closing_at: string } | null; pick: { playerId: number; name: string; injuryStatus: string | null } | null; sent: Set<string> }): { kind: "no_pick_2h" | "no_pick_30m" | "injury"; key: string; title: string; body: string }[]` — clé d'envoi `${kind}|${key}` dans `sent` ;
  - `POST /api/reminders` (et `GET` identique pour tester à la main) : 401 sans `Authorization: Bearer ${REMINDERS_SECRET}` (comparaison à temps constant, `crypto.timingSafeEqual` sur des buffers de même longueur) ; sinon calcule les rappels dus pour la soirée du deck, **réserve** chaque rappel en insérant dans `reminders_sent` (conflit d'unicité → déjà envoyé, on saute) puis appelle `notifyAll` ; renvoie `{ sent: n }`.

- [ ] **Step 1: Tests** — `web/src/lib/reminders.test.ts` :

```ts
import { describe, expect, it } from "vitest";
import { dueReminders } from "./reminders";

const night = { date: "2026-10-21", closing_at: "2026-10-21T22:00:00Z" }; // 00:00 Paris
const at = (iso: string) => new Date(iso);
const kinds = (r: ReturnType<typeof dueReminders>) => r.map((x) => x.kind);

describe("dueReminders", () => {
  it("rien avant −2 h", () => {
    expect(dueReminders({ now: at("2026-10-21T19:30:00Z"), night, pick: null, sent: new Set() })).toEqual([]);
  });
  it("−2 h sans pick", () => {
    expect(kinds(dueReminders({ now: at("2026-10-21T20:05:00Z"), night, pick: null, sent: new Set() }))).toEqual(["no_pick_2h"]);
  });
  it("−30 min : seulement le second rappel, même si le premier a été sauté", () => {
    expect(kinds(dueReminders({ now: at("2026-10-21T21:35:00Z"), night, pick: null, sent: new Set() }))).toEqual(["no_pick_30m"]);
  });
  it("déjà envoyé : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T20:05:00Z"), night, pick: null, sent: new Set(["no_pick_2h|"]) })).toEqual([]);
  });
  it("après la fermeture : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T22:00:00Z"), night, pick: null, sent: new Set() })).toEqual([]);
  });
  it("pas de soirée : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T21:35:00Z"), night: null, pick: null, sent: new Set() })).toEqual([]);
  });
  it("pick posé : pas de rappel d'oubli", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: null };
    expect(dueReminders({ now: at("2026-10-21T21:35:00Z"), night, pick, sent: new Set() })).toEqual([]);
  });
  it("alerte blessure à tout moment avant la fermeture, une fois par statut", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: "Out" };
    const r = dueReminders({ now: at("2026-10-21T10:00:00Z"), night, pick, sent: new Set() });
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: "injury", key: "7:Out" });
    expect(r[0].body).toContain("00:00");
    expect(dueReminders({ now: at("2026-10-21T11:00:00Z"), night, pick, sent: new Set(["injury|7:Out"]) })).toEqual([]);
  });
  it("Questionable ne déclenche rien", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: "Questionable" };
    expect(dueReminders({ now: at("2026-10-21T10:00:00Z"), night, pick, sent: new Set() })).toEqual([]);
  });
});
```

- [ ] **Step 2: Échec** — Run: `cd web && npm test` → FAIL.

- [ ] **Step 3: Implémenter `reminders.ts`**

```ts
import { HARD_OUT_STATUSES } from "@/lib/display";
import { parisTime } from "@/lib/date";

export type Reminder = { kind: "no_pick_2h" | "no_pick_30m" | "injury"; key: string; title: string; body: string };

const H2 = 2 * 60 * 60 * 1000;
const M30 = 30 * 60 * 1000;

export function dueReminders(input: {
  now: Date;
  night: { date: string; closing_at: string } | null;
  pick: { playerId: number; name: string; injuryStatus: string | null } | null;
  sent: Set<string>;
}): Reminder[] {
  const { now, night, pick, sent } = input;
  if (!night) return [];
  const closing = new Date(night.closing_at).getTime();
  const t = now.getTime();
  if (t >= closing) return [];
  const at = parisTime(night.closing_at);
  const out: Reminder[] = [];
  if (!pick) {
    const kind = t >= closing - M30 ? "no_pick_30m" : t >= closing - H2 ? "no_pick_2h" : null;
    if (kind && !sent.has(`${kind}|`)) {
      out.push({ kind, key: "", title: "Pas de pick ce soir", body: `Le deck ferme à ${at}.` });
    }
  } else if (pick.injuryStatus && HARD_OUT_STATUSES.has(pick.injuryStatus)) {
    const key = `${pick.playerId}:${pick.injuryStatus}`;
    if (!sent.has(`injury|${key}`)) {
      out.push({ kind: "injury", key, title: `${pick.name} : ${pick.injuryStatus}`,
                 body: `Ton pick de ce soir est ${pick.injuryStatus}. Change avant ${at}.` });
    }
  }
  return out;
}
```

- [ ] **Step 4: Route** — `web/src/app/api/reminders/route.ts` (`export const runtime = "nodejs"`, `dynamic = "force-dynamic"`) : vérifie le secret (absent de l'environnement → 500 « REMINDERS_SECRET manquant », journalisé sans valeur) ; `adminClient()` ; soirée = `nights` à `deckDate()` (non fantôme, `n_eligible_games > 0`) sinon `{ sent: 0 }` ; pick de cette date avec `players(name, injury_status)` ; `reminders_sent` de la soirée → `sent` ; pour chaque rappel dû : `insert` dans `reminders_sent` (`night, kind, key`) ; en cas d'erreur `23505` passer au suivant ; sinon `notifyAll({ title, body, url: "/" })`. Réponse `{ sent }`. Vérifier que `web/src/proxy.ts` exclut bien `/api/` (fait en L1c).

- [ ] **Step 5: Vérifier** — Run: `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → vert.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/reminders.ts web/src/lib/reminders.test.ts web/src/app/api/reminders
git commit -m "feat(web): rappels d'oubli (−2 h, −30 min) et alerte blessure du pick, idempotents"
```

---

### Task 9: Minors du front et documentation

**Files:**
- Modify: `web/src/app/deck/page.tsx`, `web/src/app/page.tsx`, `web/src/app/picks/page.tsx`, `web/src/app/player/[id]/PickControls.tsx`, `docs/operations.md`, `docs/reactivation-saison.md`

- [ ] **Step 1: Deck** — la requête des matchs du deck filtre `game_type in ('regular','cup_final','playoffs')` (commentaire « Miroir de ELIGIBLE_TYPES ») ; le libellé devient « Les soirées des 14 prochains jours ».
- [ ] **Step 2: Erreurs silencieuses** — sur Ce soir, Deck et Picks, si une requête Supabase renvoie `error`, afficher un encart `role="alert"` « Données indisponibles pour le moment, réessaie dans quelques minutes. » au lieu d'une liste vide (ne pas masquer le reste de la page).
- [ ] **Step 3: Fiche joueur** — `PickControls` : l'état « en cours » est suivi par soirée (`pendingNight: string | null`) ; un clic ne désactive plus les autres soirées.
- [ ] **Step 4: Docs** — `docs/operations.md` : section « Rappels » (variables `NEXT_PUBLIC_VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `REMINDERS_SECRET`, `TELEGRAM_*` ; `supabase/manual/reminders_cron.sql` ; test depuis `/rappels`), avertissement « `web/.env.local` pointe la prod : en `npm run dev`, un pick ou une correction écrit en production », et la nouvelle cadence de `daily-sync.yml` (dont les heures d'hiver à décaler après le 25/10). `docs/reactivation-saison.md` : cdn.nba.com n'est plus utilisé (ESPN pour les statuts et le direct).
- [ ] **Step 5: Vérifier** — Run: `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build` → vert.
- [ ] **Step 6: Commit**

```bash
git add web/src docs
git commit -m "fix(web): deck filtré sur les matchs éligibles, erreurs de données visibles, état par soirée ; docs rappels"
```

---

### Task 10: Mise en prod (feu vert de l'utilisateur requis à chaque étape)

**Files:** aucun code ; mise à jour de `docs/reactivation-saison.md` si une étape diffère.

- [ ] **Step 1: Migrations** — `supabase db push --linked --dry-run` doit lister **023 et 024 seulement** ; puis `supabase db push --linked`. Vérifier en lecture : `select has_function_privilege('anon', 'correct_pick(date, integer)', 'execute')` → false.
- [ ] **Step 2: Secrets** — générer les clés VAPID (`npx web-push generate-vapid-keys --json > <scratchpad>/vapid.json`, jamais affiché) et un `REMINDERS_SECRET` (`openssl rand -hex 32` dans un fichier du scratchpad) ; les poser dans Vercel (`vercel env add <NOM> production < fichier`, idem preview) et dans `web/.env.local` sans les afficher ; créer le secret Vault en prod (`select vault.create_secret(...)` exécuté via `supabase db query --linked` en lisant la valeur depuis le fichier, sans l'écho) ; supprimer les fichiers du scratchpad ensuite.
- [ ] **Step 3: Déployer** — `cd web && vercel --prod --yes` ; vérifier `curl -s -o /dev/null -w "%{http_code}" https://ttfl-advisor.vercel.app/sw.js` → 200, `/rappels` → 200, `curl -X POST .../api/reminders` sans secret → 401.
- [ ] **Step 4: Cron** — appliquer `supabase/manual/reminders_cron.sql` en prod ; vérifier `select jobname, schedule from cron.job` et, 15 min plus tard, `select status_code from net._http_response order by id desc limit 1` → 200.
- [ ] **Step 5: Test utilisateur sur l'iPhone** — PWA installée depuis Safari, `/rappels` → « Activer les rappels » → « Envoyer une notification de test ». Si la notification n'arrive pas : mettre en place Telegram (l'utilisateur crée le bot via @BotFather, pose `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans Vercel lui-même) et refaire le test.
- [ ] **Step 6: Workflow** — le push sur `main` active les nouveaux horaires du soir ; lancer un run manuel `gh workflow run daily-sync.yml` et vérifier qu'il n'y a plus d'avertissement CDN.
- [ ] **Step 7: Clôture** — merge de la branche dans `main`, push, mise à jour de la mémoire projet.
