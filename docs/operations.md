# Exploitation (sync, structure, commandes)

## Sources de données

| Besoin | Source | Auth |
|--------|--------|------|
| Box scores, scoreboard du jour | `cdn.nba.com` | Headers User-Agent + Referer |
| Stats avancées, splits, game logs historiques | `nba_api` (Python wrapper de stats.nba.com) | Aucune |
| Blessures et statuts joueurs | ESPN `/nba/injuries` (endpoint global) | Aucune |
| Calendrier des playoffs | `cdn.nba.com/staticData/scheduleLeagueV2.json` | Aucune |

---

## Rythme de synchronisation (cron)

Le sync principal tourne via **GitHub Actions** (`.github/workflows/daily-sync.yml`) **4 fois par jour** (07 h / 12 h / 17 h / 22 h, heure de Paris). Un cron local complète à 23 h 50 pour le refresh des rosters (`stats.nba.com` bloque les IPs GitHub). Hors saison, les deux sont désactivés.

| Heure | Rôle |
|-------|------|
| **07 h** | Résultats de la veille (box scores), MAJ des actual_score des picks, MAJ des standings séries. Refresh team_defense 1x/jour. |
| **12 h** | Schedule du soir confirmé. Premières injury reports. Recos préliminaires. |
| **17 h** | Injury updates finaux (GTD résolus). **Recos définitives du soir.** |
| **22 h** | Late scratches, changements de dernière minute. Update recos si besoin. |

À chaque sync, le cron :

1. Fetch le scoreboard du jour (cdn.nba.com)
2. Reload le schedule (30 jours à venir)
3. Re-seed les séries playoffs (idempotent, extrait les wins depuis `seriesText`)
4. (7h uniquement) Recalcule team_defense depuis les game_logs
5. Fetch les blessures ESPN (tous les teams)
6. Update aggregates pour les joueurs qui jouent ce soir
7. Score tous les joueurs disponibles
8. Applique la couche stratégie
9. Génère les argumentaires (top 50)
10. Push les recommandations vers Supabase
11. Calcule le plan hebdomadaire optimal et le push

Le refresh des **rosters** (nba_api) est à part : gated par un cache de 72 h et exécuté par le run local de 23 h 50 uniquement (stats.nba.com bloque les IPs GitHub).

Logs : `/tmp/ttfl-sync.log`

---

## Structure du code

```
nba-fantasy/
├── sync/                              # Backend Python
│   ├── config.py                      # Env vars, constantes (WEIGHTS, FATIGUE, etc.)
│   ├── ttfl.py                        # Calcul du score TTFL (pure function)
│   ├── fetcher.py                     # Fetchers cdn.nba.com + nba_api
│   ├── injuries.py                    # Fetcher ESPN blessures (endpoint global)
│   ├── load_schedule.py               # Charge le schedule NBA 30 jours
│   ├── seed_playoffs.py               # Parse seriesText → table series
│   ├── compute_team_defense.py        # Agrège TTFL encaissé par équipe × poste
│   ├── db.py                          # Client Supabase + CRUD helpers
│   ├── scoring.py                     # Moteur de scoring 6 facteurs
│   ├── strategy.py                    # Tiers, élimination, burn-or-save, réservation elites
│   ├── personal_strategy.py           # Save tax par équipe/rang (désactivée, cf docs/moteur.md)
│   ├── future.py                      # best_future_score (scan 7 jours)
│   ├── advisor.py                     # Argumentaires POUR/CONTRE/VERDICT
│   ├── weekly_plan.py                 # Algo hongrois (plan hebdo)
│   ├── matchups.py                    # Matchups défensifs joueur vs joueur (box scores raw)
│   ├── matchup_report.py              # Rapport matchups d'un match
│   ├── backfill_matchups.py           # Backfill historique des matchups
│   ├── backfill_dnp.py                # Backfill des DNP dans les game logs
│   ├── seed.py                        # Seed initial des game logs (20 équipes playoffs + play-in)
│   ├── seed_personal_strategy.py      # Seed des tables team_outlook / player_team_rank
│   └── main.py                        # Orchestrateur cron
├── tests/                             # 97 tests unitaires (pytest)
├── web/                               # Frontend Next.js 16
│   ├── src/app/                       # Pages (App Router)
│   │   ├── page.tsx                   # "Ce soir"
│   │   ├── player/[id]/page.tsx       # Fiche joueur
│   │   ├── games/                     # Matchs (calendrier, résultats, matchups défensifs)
│   │   ├── series/                    # Détail d'une série playoffs
│   │   ├── picks/                     # Mes picks (2 onglets)
│   │   ├── strategy/page.tsx          # Stratégie + plan hebdo
│   │   ├── injuries/                  # Blessés par équipe
│   │   └── api/                       # Route handlers (server-side)
│   ├── src/components/                # RecommendationCard, BottomNav, etc.
│   ├── src/lib/supabase.ts            # Client Supabase
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
SUPABASE_KEY=sb_publishable_xxx
SUPABASE_SERVICE_KEY=sb_secret_xxx
```

`web/.env.local` :
```
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_xxx
```

### Exécution

```bash
# Sync manuel
source venv/bin/activate && python -m sync.main

# Tests
python -m pytest tests/ -v

# Seed initial des game logs (fait 1 fois au départ)
python -m sync.seed

# Refresh manuel de team_defense
python -m sync.compute_team_defense

# Refresh manuel du plan hebdo
python -m sync.weekly_plan

# Frontend dev
cd web && npm run dev

# Deploy Vercel
cd web && npx vercel --prod
```

### Crontab local (complément du GitHub Action)

Un seul run local par jour, dédié au refresh des rosters (stats.nba.com bloque les IPs GitHub) :

```
50 23 * * * cd /path/to/nba-fantasy && venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
```

## Tests SQL

Les fonctions et triggers SQL (migrations 017+) sont testés sur un Postgres jetable, reconstruit à chaque session de tests depuis `schema.sql` et toutes les migrations.

```bash
docker run -d --rm --name ttfl-pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -v
docker stop ttfl-pg
```

Sans `TEST_DATABASE_URL`, ces tests sont ignorés. En CI, un service Postgres les fait tourner à chaque push.
