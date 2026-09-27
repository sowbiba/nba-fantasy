# Exploitation (sync, structure, commandes)

## Sources de données

| Besoin | Source | Auth |
|--------|--------|------|
| Scoreboard du jour (statuts, scores), box score en direct | ESPN `site.api.espn.com` (scoreboard + summary) | Aucune |
| Calendrier (35 jours à venir), historique de la saison (box scores) | `nba_api` (Python wrapper de stats.nba.com), depuis le PC local uniquement | Aucune |
| Blessures et statuts joueurs | ESPN `/nba/injuries` (endpoint global) | Aucune |

`cdn.nba.com` n'est plus appelé par aucun job (`daily_sync`, `local_nightly`) depuis 2026-09 : il renvoie 403 partout (PC comme GitHub Actions). Le code (`engine/io/nba.py`) reste dans le repo mais n'est plus utilisé. Voir `docs/reactivation-saison.md`.

---

## Rythme de synchronisation (cron)

Le sync principal tourne via **GitHub Actions** (`.github/workflows/daily-sync.yml`) : 3 passages dans la journée (07 h / 12 h / 17 h, heure de Paris) puis un passage **toutes les heures, de 18 h à minuit (été) ou 17 h à 23 h (hiver)** (blessures, P(joue), plan) pendant que les matchs se jouent en Europe. Un cron local complète à 23 h 50 pour les effectifs et le calendrier (`stats.nba.com` bloque les IPs GitHub). Hors saison, les deux sont désactivés.

Les horaires du yml sont en UTC (l'heure du cron GitHub Actions) : `0 5,10,15 * * *` (07/12/17 h Paris) et `0 16-22 * * *` (toutes les heures). Cette plage couvre à la fois l'heure d'été (CEST = UTC+2 : 18 h→00 h Paris) et l'heure d'hiver (CET = UTC+1 : 17 h→23 h Paris) — aucun changement n'est nécessaire au passage d'heure (voir le commentaire en tête de `daily-sync.yml`).

`daily_sync` (GitHub Actions) n'appelle plus `cdn.nba.com` (403 partout) : les statuts/scores du jour et de la veille viennent d'ESPN.

1. Scoreboard ESPN de J-1 et J (statuts, scores) → mise à jour de `games`
2. Score les picks non encore scorés dont le match est réglé (`score_picks`)
3. Fetch les blessures ESPN (tous les teams) et met à jour `players`
4. Recalcule les agrégats/profils des joueurs actifs, le facteur défense
5. Reconstruit les soirées (`nights`) sur la fenêtre chargée par `local_nightly`
6. Applique la couche stratégie et génère les recommandations + argumentaires du soir
7. Calcule le plan 30 jours et le push

Chaque étape réseau peut échouer sans faire tomber le job (décision sur les données en base, échec noté dans les `warnings` du log).

Le run local (`local_nightly`, cron 23 h 50, PC) est à part : effectifs des 30 équipes, calendrier (35 jours à venir, stats.nba.com), historique de la saison via `LeagueGameLog` (seule source de box scores, le CDN NBA n'est plus utilisé), puis `score_picks` sur les picks concernés par ce chargement, et les matchups bruts défenseur/joueur.

Logs : `/tmp/ttfl-local.log`

---

## Structure du code

```
nba-fantasy/
├── engine/                             # Backend Python
│   ├── config.py                      # Env vars, constantes
│   ├── rules/                         # Règles TTFL pures (cooldown, scoring, calendrier)
│   ├── stats/                         # Projection, P(joue), agrégats, team_defense
│   ├── strategy/                      # Optimiseur d'affectation (planner), horizon SR
│   ├── explain/                       # Argumentaires et libellés
│   ├── io/                            # Supabase, cdn.nba.com, stats.nba.com, ESPN (fetch/push)
│   └── jobs/
│       ├── daily_sync.py              # Passage complet (GitHub Actions)
│       ├── local_nightly.py           # Effectifs + LeagueGameLog + matchups (PC local)
│       └── backtest.py                # Backtest lecture seule + rapport Markdown (voir § Backtest)
├── tests/                             # tests unitaires (pytest)
├── web/                               # Frontend Next.js 16
│   ├── src/app/                       # Pages (App Router)
│   │   ├── page.tsx                   # "Ce soir"
│   │   ├── player/[id]/page.tsx       # Fiche joueur
│   │   ├── games/                     # Matchs (calendrier, résultats, matchups défensifs)
│   │   ├── series/                    # Détail d'une série playoffs
│   │   ├── picks/                     # Mes picks (2 onglets)
│   │   ├── strategy/page.tsx          # Stratégie + plan hebdo
│   │   ├── injuries/                  # Blessés par équipe
│   │   └── api/                       # Route handlers (server-side : reminders, live-box-score)
│   ├── src/components/                # RecommendationCard, BottomNav, etc.
│   ├── src/lib/supabase/              # Clients Supabase (public/server/admin)
│   └── src/types/index.ts             # Types TypeScript partagés
├── supabase/
│   ├── schema.sql                     # Schema initial
│   └── migrations/                    # Migrations additionnelles
├── ttfl-stats/                        # Mini-site bookmarklet TTFL (standalone)
└── docs/superpowers/                  # Spec + plan d'implémentation
```

### Design system frontend

- **Typography** : Bebas Neue (display) + Space Grotesk (body)
- **Accent** : ember-orange (#ff5b1f) + gold (#f7c948)
- **Surface** : noir profond avec glow radial + grain
- Tokens CSS dans `web/src/app/globals.css` (`--color-flame`, `--radius-card`, `--shadow-elite`...)
- Classes utilitaires : `.flame-text`, `.gold-text`, `.stagger`, `.animate-pulse-red`, etc.

---

## Commandes utiles

### Setup

```bash
# Backend Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd web && npm install
```

### Variables d'environnement

`.env` à la racine :
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_xxx
```

`web/.env.local` :
```
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_xxx
```

**Attention : `web/.env.local` pointe la prod. En `npm run dev`, un pick ou une correction écrit en production.**

Une soirée fermée dès le premier tip-off (avant minuit Paris) ne peut être corrigée qu'après minuit Paris : `correct_pick` s'applique aux soirées passées, et la page Picks n'offre "Corriger" que pour les dates antérieures à aujourd'hui (M9, revue finale L2a).

### Exécution

```bash
# Sync manuel (tel que GitHub Actions)
source venv/bin/activate && python -m engine.jobs.daily_sync

# Job local (effectifs, calendrier stats.nba.com, LeagueGameLog, tel que le cron local)
python -m engine.jobs.local_nightly

# Chargement d'une saison complète (une fois) :
./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26

# Tests
python -m pytest tests/ -v

# Frontend dev — écrit en prod (voir l'avertissement ci-dessus)
cd web && npm run dev

# Deploy Vercel
cd web && npx vercel --prod
```

### Crontab local (complément du GitHub Action)

Un seul run local par jour, dédié aux effectifs et au calendrier (stats.nba.com bloque les IPs GitHub) :

```
50 23 * * * cd /home/isow/workspace/perso/nba-fantasy && ./venv/bin/python -m engine.jobs.local_nightly >> /tmp/ttfl-local.log 2>&1 || { echo "$(date '+\%F \%T') TTFL local KO" >> /home/isow/ttfl-sync-failures.log; DISPLAY=:0 notify-send -u critical "TTFL local KO" 2>/dev/null; }
```

## Backtest

`engine/jobs/backtest.py` simule `best_available` et `plan` (dans les deux modes de blessures, et un ou plusieurs `decay` pour `plan`) sur une fenêtre passée, et compare le résultat aux vrais picks de l'utilisateur sur les mêmes soirées. Rapport Markdown en sortie, pas d'interface web.

```bash
./venv/bin/python -m engine.jobs.backtest --season 2025-26 --from 2026-02-01 --to 2026-04-12
# --decay 0.97,0.985,1.0   : variantes de decay pour `plan` (diagnostic, en plus du décay par défaut)
# --out docs/backtest/2025-26-sr.md   : chemin du rapport (défaut : docs/backtest/<saison>-sr.md)
```

**Lecture seule** : le job n'appelle que les méthodes `load_*` de `SupabaseRepo` — aucune écriture, aucune ligne `sync_log` (contrairement à `daily_sync`/`local_nightly`). Testé par `tests/jobs/test_backtest_job.py` avec un faux repo dont seules les méthodes de lecture nécessaires sont déléguées ; tout le reste (écritures, `sync_log`, futures méthodes) lève une `AssertionError`.

**Limites** :
- Aucun historique des statuts de blessures en base : le rapport donne deux bornes plutôt qu'une vérité unique — `none` (personne n'est jamais déclaré blessé : pessimiste) et `dnp_oracle` (un joueur ayant DNP le soir même après avoir joué au moins un de ses 5 derniers matchs est déclaré « Out » : optimiste). L'utilisateur, lui, avait l'information du jour : la comparaison équitable est entre les deux bornes, pas contre l'une des deux isolément.
- La saison 2024-25 n'est pas chargée en base → fenêtre par défaut février-avril de la saison en cours (peu d'historique de profils avant février).
- Si la fenêtre se termine avant la fin d'un mois x2 : asymétrie en faveur de `plan` pour ce mois — `best_available` (référence naïve, x2 sur la dernière soirée du mois) perd le x2 hors fenêtre, alors que `plan` (planificateur MILP, S3) peut le poser plus tôt dans le mois s'il voit la fin du mois dans son horizon de 35 jours — signalé dans le rapport quand c'est le cas.
- Comparaison restreinte à la saison régulière (R14, R10 : pas de x2 en playoffs).
- Le rapport montre la moyenne réelle de l'utilisateur deux fois : via `picks.actual_score` (officiel, ce que l'app a enregistré) et via les logs (`user_result`, notée comme les simulations) — avec le nombre de soirées où les deux diffèrent.

## Tests SQL

Les fonctions et triggers SQL (migrations 017+) sont testés sur un Postgres jetable, reconstruit à chaque session de tests depuis `schema.sql` et toutes les migrations.

```bash
docker run -d --rm --name ttfl-pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -v
docker stop ttfl-pg
```

Sans `TEST_DATABASE_URL`, ces tests sont ignorés. En CI, un service Postgres les fait tourner à chaque push.

## Rappels (Web Push + Telegram)

Deux rappels par soirée si activés : oubli de pick (−2 h puis −30 min avant `closing_at`) et alerte blessure/indisponibilité du joueur pické. Web Push en priorité, Telegram en secours si `notifyAll` ne délivre rien.

**Variables d'environnement** (Vercel, jamais commitées) :

| Variable | Rôle |
|----------|------|
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | Clé publique VAPID, exposée au navigateur pour `pushManager.subscribe` |
| `VAPID_PRIVATE_KEY` | Clé privée VAPID, côté serveur uniquement (`web/src/lib/notify.ts`) |
| `REMINDERS_SECRET` | Secret Bearer attendu par `POST /api/reminders` (comparaison à temps constant) |
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram, secours si aucun push n'est délivré |
| `TELEGRAM_CHAT_ID` | Chat Telegram cible pour le secours |

**Stockage** : migration 024 (`push_subscriptions`, `reminders_sent`), accès par la clé service uniquement (RLS activée, pas de policy). `web/public/sw.js` est le service worker écrit à la main (pas de génération) qui reçoit les push et affiche la notification.

**Déclenchement** : `supabase/manual/reminders_cron.sql`, à exécuter une fois en prod après avoir créé le secret dans Vault (`select vault.create_secret('<valeur REMINDERS_SECRET>', 'reminders_secret');`). Il installe un job `pg_cron` (`ttfl-reminders`, toutes les 15 min) qui `POST` sur `https://ttfl-advisor.vercel.app/api/reminders` avec `Authorization: Bearer <secret Vault>`. La route (`web/src/app/api/reminders/route.ts`) répond `{ sent: n }`, `401` si le secret ne correspond pas, `500` si `REMINDERS_SECRET` ou `SUPABASE_SERVICE_KEY` est absente côté serveur — elle ne doit jamais planter, `pg_cron` l'appelle sans surveillance.

**Test manuel** : se connecter (menu Picks → Connexion), aller sur `/rappels`, « Activer les rappels », puis « Envoyer une notification de test ». Sur iPhone, l'app doit d'abord être ajoutée à l'écran d'accueil (Web Push indisponible dans Safari hors PWA installée).
