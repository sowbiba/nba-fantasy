# TTFL Advisor

Outil d'aide à la décision pour la **TrashTalk Fantasy League** (TTFL). L'app te recommande chaque soir les meilleurs picks parmi les joueurs NBA disponibles, avec un argumentaire détaillé. En playoffs, un moteur stratégique protège tes franchise-players pour les tours suivants.

App live : **https://web-sigma-one-74.vercel.app** (PWA installable sur mobile)

---

## Table des matières

1. [Architecture](#architecture)
2. [Sources de données](#sources-de-données)
3. [Modes de jeu](#modes-de-jeu)
4. [Le moteur de scoring (6 facteurs)](#le-moteur-de-scoring-6-facteurs)
5. [Ajustements contextuels](#ajustements-contextuels)
6. [Couche stratégie playoffs](#couche-stratégie-playoffs)
7. [Plan hebdomadaire optimal](#plan-hebdomadaire-optimal)
8. [Écrans de l'app](#écrans-de-lapp)
9. [Rythme de synchronisation (cron)](#rythme-de-synchronisation-cron)
10. [Structure du code](#structure-du-code)
11. [Commandes utiles](#commandes-utiles)
12. [Tuning des paramètres](#tuning-des-paramètres)

---

## Architecture

```
Sources de données                    Stockage                    Frontend
─────────────────                    ─────────                   ────────
cdn.nba.com (box scores, schedule)
nba_api (stats avancées, splits)   →  Python cron  →  Supabase  →  Next.js PWA
ESPN (blessures, statuts)             (machine locale)  (cloud)      (Vercel)
```

- **Script Python** tourne en local via cron, 4x/jour
- **Supabase** (PostgreSQL gratuit) stocke tout : stats, recos, picks, séries, plan hebdo
- **Next.js PWA** sur Vercel, accessible de n'importe où

---

## Sources de données

| Besoin | Source | Auth |
|--------|--------|------|
| Box scores, scoreboard du jour | `cdn.nba.com` | Headers User-Agent + Referer |
| Stats avancées, splits, game logs historiques | `nba_api` (Python wrapper de stats.nba.com) | Aucune |
| Blessures et statuts joueurs | ESPN `/nba/injuries` (endpoint global) | Aucune |
| Calendrier des playoffs | `cdn.nba.com/staticData/scheduleLeagueV2.json` | Aucune |

---

## Modes de jeu

### Saison régulière
- Un joueur pické est indisponible **30 jours**
- 7 picks max par semaine
- Scoring basé sur la performance pure (6 facteurs)

### Playoffs
- Un joueur ne peut être pické qu'**une seule fois** sur toute la durée des playoffs
- Scoring = performance + couche stratégie (capital joueurs + réservation des elites)
- Prise en compte du home court, de l'avancement des séries, du risque d'élimination

---

## Le moteur de scoring (6 facteurs)

Pour chaque joueur qui joue ce soir, le moteur calcule un **score de performance estimé** à partir de 6 facteurs pondérés.

| Facteur | Poids | Formule / Logique |
|---------|-------|-------------------|
| **Moyenne TTFL pondérée** | 35 % | `(L5 × 3 + L10 × 1 + L20 × 2) / 6` — privilégie la forme récente |
| **Matchup défensif** | 25 % | `opponent_ttfl_at_position / league_avg` — facteur multiplicatif |
| **Home / Away split** | 10 % | Delta entre son avg home (ou away) et son avg saison |
| **Fatigue / Back-to-back** | 10 % | B2B = -8 %, 3 matchs en 4 jours = -12 %, 3+ jours de repos = +3 % |
| **Tendance récente** | 10 % | Régression linéaire sur L10. Pente positive = bonus, négative = malus (capé ±10 %) |
| **Floor / Ceiling (régularité)** | 10 % | CV = stddev/avg. Faible CV = bonus (fiable), fort CV = malus (volatile) |

### Zoom sur la moyenne pondérée

- **L5** = moyenne TTFL des 5 derniers matchs (forme ultra-récente)
- **L10** = moyenne des 10 derniers
- **L20** = moyenne des 20 derniers

Poids : `L5 × 3 + L10 × 1 + L20 × 2`, divisé par 6.

Exemple Jokic : L5=58, L10=55, L20=52 → `(58×3 + 55×1 + 52×2) / 6 = 55.5`

### Formule TTFL officielle (pour référence)

```
TTFL = (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM)
     - (TOV + FG_miss + 3P_miss + FT_miss)
```

### Assemblage final

Le score est calculé comme un produit pondéré :

```
base        = weighted_average(L5, L10, L20)
multiplier  = matchup ^ 0.385
            × home_away ^ 0.154
            × fatigue ^ 0.154
            × trend ^ 0.154
            × consistency ^ 0.154
final_score = base × multiplier
```

(Les exposants sont les poids normalisés à somme 1.)

---

## Ajustements contextuels

### Impact des blessures coéquipiers (usage boost)

Si un coéquipier "majeur" d'une équipe est OUT, les autres joueurs bénéficient d'un boost d'usage implicite.

**Détection** : un coéquipier est considéré comme majeur s'il est dans le **top 3 de son équipe en `avg_ttfl_season`**. Surfacé dans l'UI par un badge violet "⚡ Usage boost" et une section dédiée "Opportunités blessures" sur la page d'accueil.

### Statut du joueur lui-même

| Statut ESPN | Impact |
|-------------|--------|
| `Out` | Exclu du classement |
| `Doubtful` | Exclu (trop risqué) |
| `Questionable` | Flag ⚠️ + malus -15 % |
| `Day-To-Day` (GTD) | Flag 🔶 + malus -10 % |

---

## Couche stratégie playoffs

Cette couche s'active **uniquement en mode playoffs**.

### Classification des tiers

À chaque génération, les joueurs disponibles sont triés par score de performance et classés :

| Rang ce soir | Tier | Stars |
|--------------|------|-------|
| 1 à 10 | **Elite** | ★★★ (or) |
| 11 à 25 | **Solide** | ★★ (bleu) |
| 26 à 50 | **Filler** | ★ (gris) |

Les tiers sont **relatifs au soir**, pas absolus. Une nuit avec peu de matchs : un joueur moyen peut être Elite. Une nuit dense : un très bon joueur peut tomber en Solide.

### Estimation du calendrier restant

Pour chaque série active, le moteur estime le nombre de jours de match restants :

```
pour chaque série active :
    max_wins = max(home_wins, away_wins)
    min_games_left = 4 - max_wins
    max_games_left = 7 - (home_wins + away_wins)
    est_remaining = (min_games_left + max_games_left) / 2

pour les tours futurs (non démarrés) :
    +6 games estimés par tour restant

total_game_days ≈ total_games × 0.7  (~60-70% des jours calendaires ont des matchs)
```

### Détection du risque d'élimination

Une équipe est classée selon son risque d'être éliminée ce soir :

| Série (points de vue du joueur) | Risque | Effet |
|---------------------------------|--------|-------|
| Son équipe a déjà 3 défaites | **Critical** | +15 % sur le score + verdict `"JOUE-LE CE SOIR"` forcé |
| Son équipe a 2 défaites et n'est pas en avance | **High** | +5 % sur le score |
| Autre | None | aucun ajustement |

Le verdict d'un joueur en `critical` **force le burn** même si l'algo aurait préféré le garder. Raison : *"Si tu ne l'utilises pas maintenant, tu le perds pour tout le reste des playoffs."*

### Bonus / malus stratégiques

Appliqués directement sur le score de performance :

| Condition | Modificateur |
|-----------|--------------|
| Match à domicile | +3 % |
| Domicile + série serrée (écart ≤ 1) | +2 % supplémentaires |
| Match d'élimination (3-X, tier != filler) | +8 % |
| Elite dont le ratio elites/jours est < 0.2 | -5 % (discourage le burn tardif) |
| Filler quand ratio < 0.25 | +3 % (encourage à jouer filler les soirs pauvres) |
| Match à l'extérieur | -3 % |

### Burn or save ?

Pour chaque joueur, le moteur calcule :

- `tonight_score` = score estimé ce soir (après tous les facteurs)
- `best_future_score` = meilleur score estimé sur les **7 prochains jours** (via scan de son calendrier)

Décision :

```
if elimination == "critical":
    JOUE_LE  # force absolue
elif best_future_score > tonight_score × 1.10:  # BURN_THRESHOLD
    GARDE_LE
elif elites_remaining ≤ 2 and game_days_remaining > 10:
    JOUE_LE seulement si tonight_score ≥ best_future_score
else:
    JOUE_LE
```

---

## Plan hebdomadaire optimal

L'app calcule automatiquement une **affectation optimale** de joueurs aux jours de la semaine via l'**algorithme hongrois** (`scipy.optimize.linear_sum_assignment`).

### Problème

Tu as :
- N jours de matchs dans la semaine à venir
- M joueurs éligibles (non pickés, non blessés, leur équipe joue)
- Pour chaque couple (jour, joueur), un score estimé

**Contrainte** : 1 pick par jour, chaque joueur au max 1 fois sur toute la fenêtre.

**Objectif** : maximiser le score total.

C'est un **problème d'affectation** classique, résolu de façon optimale en O(n³) par l'algo hongrois.

### Réservation des elites pour les tours avancés

Sans cette couche, l'algo hongrois brûlerait facilement Jokic au Game 2 du Round 1, alors que DEN a 3 tours potentiels devant lui. Pour éviter ça :

**Pénalité de réservation** :
```
reservation = player_elite_factor × team_potential × round_factor × 60 %
final_score = perf_score × (1 − reservation)
```

Où :

| Composante | Formule |
|------------|---------|
| `player_elite_factor` | `min(1.0, (avg_season − 32) / 23)` — 32 = seuil, 55 = elite max (ex: Jokic) |
| `team_potential` | 1.0 pour tête de série R1 (home court), 0.5 pour seed 5-8, 0.3 pour play-in |
| `round_factor` | 1.0 en R1, 0.55 en R2, 0.2 en R3 (Conf Finals), 0.0 en Finales |
| `MAX_RESERVATION_PENALTY` | 0.60 (plafond à -60 %) |

**Effet** :
- Jokic DEN R1 : `1.0 × 1.0 × 1.0 × 60 % = 60 %` → score 40 devient 16 → éjecté du plan R1
- LeBron LAL R1 : `0.43 × 1.0 × 1.0 × 60 % ≈ 26 %` → score 35 devient 26 → peut passer si matchup juteux
- Jalen Johnson ATL R1 : `0.14 × 0.5 × 1.0 × 60 % ≈ 4 %` → quasi-négligeable → reste éligible

**L'élimination critique annule toujours la réservation** — si son équipe peut être out ce soir, le moteur le recommandera quand même.

### Réglage

Les constantes clés sont dans `sync/weekly_plan.py` :

```python
MAX_RESERVATION_PENALTY = 0.60
ROUND_RESERVATION_FACTOR = {1: 1.0, 2: 0.55, 3: 0.2, 4: 0.0}
TEAM_POTENTIAL_TOP_SEED = 1.0
TEAM_POTENTIAL_LOW_SEED = 0.5
TEAM_POTENTIAL_UNKNOWN = 0.3
```

Baisser `MAX_RESERVATION_PENALTY` à 0.45 rendra les elites plus présents en R1. Le monter à 0.75 les exclura presque tous.

---

## Écrans de l'app

### `/` — Ce soir (accueil)

- Header "CE SOIR" + date + nombre de matchs + bouton refresh
- Pastille de dernière synchro (verte < 12h, orange sinon)
- Matchs du soir repliables (série, game number, tip-off)
- Bandeau stratégie : capital restant (X elites, Y solides, Z fillers) + jours restants estimés
- **Opportunités blessures** (violet) : top 3 joueurs avec teammate OUT
- **Top 3 recommandations** : cartes avec rang, score estimé, matchup, tier, tags
- Liste complète des 50 joueurs classés (repliable)

### `/player/[id]` — Fiche joueur

- Identité + position + match du soir + score estimé
- 3 stats : avg TTFL L5, avg saison, floor · ceiling
- Blocs **POUR** / **CONTRE** / **VERDICT** détaillés
- Bouton "Picker ce joueur ce soir"

### `/picks` — Mes picks

- 2 onglets : **Saison régulière** / **Playoffs** avec totaux séparés
- Stats : moyenne, meilleur, pire pick
- Historique complet des picks avec badge x2 bonus si applicable

### `/strategy` — Stratégie

- **Capital restant** (elite/solide/filler)
- **Plan de la semaine** : 1 joueur assigné par jour via algo hongrois, score estimé, badge élimination si applicable
- **Calendrier 7 jours** : barres d'intensité, badge BEST sur le soir premium
- **Séries en cours** : score, games restants estimés, badge ELIM si 3-X

### `/injuries` — Blessés

- Groupés par équipe (header aux couleurs NBA officielles)
- Repliables (fermés par défaut) — bouton "Tout déplier"
- Par joueur : nom, blessure (ex: "Achilles (Right Leg)"), commentaire ESPN, date de retour, date de mise à jour ESPN

---

## Rythme de synchronisation (cron)

Le cron tourne sur ta machine locale (crontab) **4 fois par jour** :

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
│   ├── strategy.py                    # Tiers, élimination, burn-or-save
│   ├── future.py                      # best_future_score (scan 7 jours)
│   ├── advisor.py                     # Argumentaires POUR/CONTRE/VERDICT
│   ├── weekly_plan.py                 # Algo hongrois + réservation elites
│   ├── seed.py                        # Seed initial des game logs (22 teams)
│   └── main.py                        # Orchestrateur cron
├── tests/                             # 38 tests unitaires (pytest)
├── web/                               # Frontend Next.js 16
│   ├── src/app/                       # Pages (App Router)
│   │   ├── page.tsx                   # "Ce soir"
│   │   ├── player/[id]/page.tsx       # Fiche joueur
│   │   ├── picks/                     # Mes picks (2 onglets)
│   │   ├── strategy/page.tsx          # Stratégie + plan hebdo
│   │   └── injuries/                  # Blessés par équipe
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

### Crontab installé

```
0 7 * * * cd /home/isow/workspace/perso/nba-fantasy && venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 12 * * * cd /home/isow/workspace/perso/nba-fantasy && venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 17 * * * cd /home/isow/workspace/perso/nba-fantasy && venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
0 22 * * * cd /home/isow/workspace/perso/nba-fantasy && venv/bin/python -m sync.main >> /tmp/ttfl-sync.log 2>&1
```

---

## Tuning des paramètres

### Poids du scoring

`sync/config.py` :
```python
WEIGHTS = {
    "weighted_avg": 0.35,
    "matchup": 0.25,
    "home_away": 0.10,
    "fatigue": 0.10,
    "trend": 0.10,
    "consistency": 0.10,
}
```

Ajuster ces poids change directement la philosophie du moteur. Ex: augmenter `matchup` à 0.35 et baisser `weighted_avg` à 0.25 si tu veux privilégier les bons matchups sur la forme pure.

### Seuil burn-or-save

`sync/config.py` :
```python
BURN_THRESHOLD = 0.10  # 10 % de marge
```

Plus haut (ex: 0.15) = l'app économise plus les elites. Plus bas (0.05) = elle pousse à les utiliser dès qu'il y a une opportunité correcte.

### Réservation elites R1

`sync/weekly_plan.py` :
```python
MAX_RESERVATION_PENALTY = 0.60        # plafond à -60 %
ROUND_RESERVATION_FACTOR = {1: 1.0, 2: 0.55, 3: 0.2, 4: 0.0}
TEAM_POTENTIAL_TOP_SEED = 1.0
TEAM_POTENTIAL_LOW_SEED = 0.5
```

- `MAX = 0.45` → laisse plus d'elites dans le plan R1
- `MAX = 0.75` → exclut presque tous les elites des têtes de série
- Modifier `ROUND_RESERVATION_FACTOR[2]` si tu veux être plus/moins conservateur en conf semis

### Seuil "joueur éligible" au plan hebdo

`sync/weekly_plan.py`, dans `build_candidates` :
```python
if season_avg < 10:
    continue
```

Ce seuil filtre les joueurs qui n'ont quasiment pas joué pour garder la matrice Hungarian raisonnable. Le baisser à 5 inclut plus de role players obscurs.

---

## Workflow recommandé

### Dimanche soir ou lundi matin — Plan de la semaine (15 min)

1. Ouvre **Stratégie** → regarde le **Plan de la semaine**
2. Copie les picks sur le site TTFL pour la semaine
3. Garde 1 slot "flex" (le moins sûr) non validé si tu hésites

### Chaque jour à 17 h — Review rapide (5 min)

1. Le cron de 17h a tourné (recos définitives)
2. Check l'onglet **Blessés** : ton joueur du soir est-il impacté ? Un coéquipier majeur adverse est-il OUT ?
3. Si changement critique → swap avec un remplaçant équivalent ou ton slot flex
4. Sinon → laisse le pick tel quel

### 3 règles anti-regret

1. **Ne change jamais par "fomo"** — un joueur qui chauffe sur Twitter n'est pas une raison de casser ton plan
2. **Swap seulement si info nouvelle** depuis ton plan (blessure annoncée, starters shake-up)
3. **Lundi matin — post-mortem 2 min** — regarde tes picks ratés, apprends, sans sur-réagir (la variance du jeu est réelle)

---

## Licence

Projet personnel — MIT
