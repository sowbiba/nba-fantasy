# TTFL Advisor — Design Spec

**Date :** 2026-04-13
**Statut :** Approuvé

## Objectif

Outil d'aide à la décision pour la TrashTalk Fantasy League (TTFL). L'app recommande chaque soir les 3 meilleurs picks parmi les joueurs NBA disponibles, avec une synthèse argumentée (pour/contre/verdict) pour chaque joueur du top 50. En playoffs, le moteur intègre une couche de stratégie pour gérer le "capital joueurs" (un joueur ne peut être pické qu'une seule fois).

Jeu en solo uniquement. Accessible depuis un téléphone (PWA), y compris hors réseau local.

## Architecture

```
Sources de données                    Stockage                    Frontend
─────────────────                    ─────────                   ────────
cdn.nba.com (box scores, schedule)
nba_api (stats avancées, splits)   →  Python cron  →  Supabase  →  Next.js PWA
ESPN (blessures, statuts)             (ta machine)    (cloud)      (Vercel)
```

- **Script Python** tourne sur la machine de l'utilisateur, exécuté 4x/jour via cron.
- **Supabase** (PostgreSQL gratuit) stocke tout : stats, recommandations, picks, séries.
- **Next.js PWA** déployée sur Vercel (gratuit), lit Supabase. Accessible de partout.

## Sources de données

| Besoin | Source | Auth |
|--------|--------|------|
| Box scores, schedule du jour | cdn.nba.com (todaysScoreboard, boxscore JSON) | Aucune (headers User-Agent + Referer requis) |
| Stats avancées, splits, game logs historiques | nba_api (Python, wraps stats.nba.com) | Aucune |
| Blessures, statuts joueurs (OUT/GTD/Questionable) | ESPN API non-officielle (/injuries par équipe) | Aucune |
| Rosters | nba_api CommonTeamRoster | Aucune |

## Modes de fonctionnement

### Saison régulière
- Un joueur pické est indisponible pendant 30 jours.
- 7 picks max par semaine.
- Scoring basé sur la performance pure (6 facteurs).

### Playoffs
- Un joueur ne peut être pické qu'une seule fois sur toute la durée des playoffs.
- Scoring performance + couche stratégie (gestion du capital joueurs).
- Prise en compte du home court advantage, de l'avancement des séries, et du calendrier restant.

## Moteur de scoring

### Étape 1 — Score de performance brut

6 facteurs pondérés, calculés pour chaque joueur qui joue ce soir :

| Facteur | Poids | Source | Logique |
|---------|-------|--------|---------|
| Moyenne TTFL pondérée | 35% | nba_api game logs | (L5 × 3 + L10 × 2 + L20 × 1) / 6. Priorise la forme récente. |
| Matchup défensif | 25% | nba_api team defense stats | Pts TTFL encaissés par l'adversaire au poste (G/F/C). Normalisé en bonus/malus %. |
| Home / Away split | 10% | nba_api splits | Moyenne TTFL home vs away du joueur. Applique le delta. |
| Fatigue / Back-to-back | 10% | Schedule NBA | B2B = malus -8%. 3 matchs en 4 jours = -12%. Repos 3j+ = bonus +3%. |
| Tendance récente | 10% | Game logs L10 | Régression linéaire sur 10 derniers matchs. Pente positive = bonus, négative = malus. |
| Floor / Ceiling (régularité) | 10% | Game logs L20 | Écart-type TTFL. Faible = fiable (bonus). Fort = volatile (malus léger). Le floor (P10) est affiché. |

**Formule TTFL :**
```
TTFL = (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM) - (TO + FG_miss + 3P_miss + FT_miss)
```
Où FG_miss = FGA - FGM, 3P_miss = 3PA - 3PM, FT_miss = FTA - FTM.

### Étape 2 — Ajustements contextuels

**Impact blessures coéquipiers :**
Si un coéquipier majeur (top 3 usage rate de l'équipe) est OUT, les coéquipiers restants reçoivent un bonus proportionnel à la redistribution d'usage estimée. Basé sur les game logs filtrés par absences du joueur blessé (stats "sans X").

**Statut du joueur lui-même :**
- OUT → exclu du classement
- Doubtful → exclu (trop risqué)
- Questionable → flag + malus -15%
- GTD → flag + malus -10%
- Minutes restriction (retour de blessure) → malus proportionnel si détecté

### Étape 3 — Couche stratégie playoffs

Activée uniquement en mode playoffs.

**Classification du capital joueurs :**
Les joueurs disponibles (non encore pickés) sont classés en tiers basés sur leur score de performance moyen :
- ★★★ Elite : top 10 disponibles
- ★★ Solide : rang 11-25
- ★ Filler : rang 26-50

**Estimation du calendrier restant :**
- Séries en cours → games restants estimés (ex: série 2-1 → estimation 2-4 games restants)
- Tours suivants → estimation basée sur le bracket
- Résultat : nombre total de jours de match estimés jusqu'à la fin des playoffs

**Home court advantage :**
L'avantage du terrain est plus marqué en playoffs qu'en saison régulière. Les games à domicile sont identifiés comme "spots premium" pour picker un joueur de cette équipe. Bonus playoff home court appliqué en plus du split home/away habituel.

**Décision burn ou save :**
Pour chaque joueur du top 50 :
- Calcul du "score ce soir" (perf estimée × contexte)
- Calcul de la "valeur future estimée" (meilleur spot prévu dans les 7 prochains jours pour ce joueur)
- Si meilleur spot futur > score ce soir + 10% → recommandation "Garde-le pour [date], [adversaire] à domicile"
- Sinon → "C'est le bon soir pour le jouer"

### Étape 4 — Génération des argumentaires

Pour chaque joueur du top 50, le moteur génère :
- **POUR** : liste d'arguments en faveur du pick ce soir (forme, matchup, home court, etc.)
- **CONTRE** : liste d'arguments contre (capital joueur, meilleur spot à venir, volatilité, etc.)
- **VERDICT** : recommandation finale contextualisée avec explication

Exemple :
> **Nikola Jokic — Score estimé : 87.2**
> ✅ POUR : En feu (62.4 avg L5), OKC encaisse le 2e plus de pts TTFL aux pivots, Game 5 à domicile série 2-2.
> ❌ CONTRE : Meilleur elite restant, 3 elites pour ~18 jours de match, finales de conf dans 8 jours.
> 💡 VERDICT : Excellent spot. JOUE-LE si DEN ferme la série. GARDE-LE si tu anticipes un Game 7 ou les finales de conf.

## Écrans

### Écran 1 — "Ce soir" (accueil)

De haut en bas :
1. **Header** : titre "TTFL Advisor" + badge mode (PLAYOFFS / REGULAR)
2. **Timestamp synchro** : pastille verte + "Dernière synchro : aujourd'hui à 17h02". Pastille orange si synchro > 12h.
3. **Matchs du soir** : bloc repliable (replié par défaut). Affiche le nombre de matchs. Déplié : équipes, numéro de game dans la série, heure tip-off.
4. **Bandeau stratégie** : résumé capital restant (X elites, Y solides, Z fillers — ~N jours de match estimés).
5. **Top 3 recommandations** : cartes avec score estimé, nom, match, tags (tier, forme, home/away, volatile), résumé 1 ligne.
6. **Lien vers les 50 joueurs classés** : scroll vers la liste complète.

### Écran 1b — Fiche joueur (tap sur un joueur du top 50)

- Header : nom, équipe, position, match du soir, score estimé, tier
- Stats clés : avg TTFL L5, avg saison, floor/ceiling
- Bloc POUR (arguments en faveur, puces)
- Bloc CONTRE (arguments contre, puces)
- Bloc VERDICT (recommandation contextuelle)
- Bouton "Picker [joueur] ce soir"

### Écran 2 — "Mes picks"

- Liste des picks avec date, match, score réel obtenu
- Stats résumées : moyenne par pick, meilleur, pire
- Mode playoffs : tous les picks de la période
- Mode saison régulière : picks de la semaine en cours + historique

### Écran 3 — "Stratégie"

- **Capital joueurs restant** : nombre par tier (Elite / Solide / Filler)
- **Calendrier 7 jours** : prochains jours de matchs avec nombre de matchs et identification du meilleur spot de la semaine
- **Séries en cours** : score de chaque série + games restants estimés

### Navigation

Barre en bas avec 3 onglets : Ce soir / Mes picks / Stratégie.

## Data model (Supabase / PostgreSQL)

### players
| Colonne | Type | Description |
|---------|------|-------------|
| id | integer PK | NBA player ID |
| name | text | Nom complet |
| team | text | Tricode (DEN, OKC...) |
| position | text | G / F / C |
| injury_status | text nullable | null, OUT, GTD, Questionable, Doubtful |
| injury_detail | text nullable | Description blessure |
| avg_ttfl_l5 | numeric | Moyenne TTFL 5 derniers matchs |
| avg_ttfl_l10 | numeric | Moyenne TTFL 10 derniers matchs |
| avg_ttfl_l20 | numeric | Moyenne TTFL 20 derniers matchs |
| avg_ttfl_season | numeric | Moyenne TTFL saison |
| stddev_ttfl | numeric | Écart-type TTFL (régularité) |
| home_avg | numeric | Moyenne TTFL à domicile |
| away_avg | numeric | Moyenne TTFL à l'extérieur |
| usage_rate | numeric | Pourcentage d'utilisation |
| updated_at | timestamptz | Dernière mise à jour |

### games
| Colonne | Type | Description |
|---------|------|-------------|
| id | text PK | NBA game ID |
| date | date | Date du match |
| home_team | text | Tricode équipe domicile |
| away_team | text | Tricode équipe extérieure |
| tip_off | timestamptz | Heure de début |
| series_id | integer FK nullable | Lien série (playoffs) |
| game_number | integer nullable | G1..G7 (playoffs) |
| status | text | scheduled, live, final |

### series
| Colonne | Type | Description |
|---------|------|-------------|
| id | serial PK | ID série |
| round | integer | 1 (R1), 2 (R2), 3 (conf finals), 4 (finals) |
| home_team | text | Équipe avec avantage terrain |
| away_team | text | Autre équipe |
| home_wins | integer | Victoires de l'équipe home |
| away_wins | integer | Victoires de l'équipe away |
| status | text | active, finished |

### game_logs
| Colonne | Type | Description |
|---------|------|-------------|
| id | serial PK | ID |
| player_id | integer FK | Lien players |
| game_id | text FK | Lien games |
| date | date | Date du match |
| pts | integer | Points |
| reb | integer | Rebonds |
| ast | integer | Passes |
| stl | integer | Interceptions |
| blk | integer | Contres |
| fgm | integer | Tirs réussis |
| fga | integer | Tirs tentés |
| tpm | integer | 3 points réussis |
| tpa | integer | 3 points tentés |
| ftm | integer | Lancers francs réussis |
| fta | integer | Lancers francs tentés |
| tov | integer | Balles perdues |
| minutes | integer | Minutes jouées |
| ttfl_score | integer | Score TTFL calculé |
| is_home | boolean | Match à domicile |

### recommendations
| Colonne | Type | Description |
|---------|------|-------------|
| id | serial PK | ID |
| date | date | Date du soir |
| player_id | integer FK | Lien players |
| rank | integer | Classement 1..50 |
| estimated_score | numeric | Score estimé final |
| perf_score | numeric | Composante performance |
| matchup_score | numeric | Composante matchup |
| strategy_score | numeric nullable | Composante stratégie (playoffs) |
| pros | jsonb | Arguments en faveur |
| cons | jsonb | Arguments contre |
| verdict | text | Recommandation textuelle |
| tier | text | elite, solid, filler |
| tags | jsonb | Tags (hot, home, volatile, reco_du_soir...) |
| computed_at | timestamptz | Timestamp du calcul |

### picks
| Colonne | Type | Description |
|---------|------|-------------|
| id | serial PK | ID |
| player_id | integer FK | Lien players |
| game_id | text FK | Lien games |
| date | date | Date du pick |
| mode | text | regular / playoffs |
| estimated_score | numeric | Score estimé au moment du pick |
| actual_score | integer nullable | Score réel (rempli après le match) |
| picked_at | timestamptz | Timestamp du pick |

### team_defense
| Colonne | Type | Description |
|---------|------|-------------|
| team | text PK | Tricode |
| vs_guards_ttfl_avg | numeric | Moy TTFL encaissée vs guards |
| vs_forwards_ttfl_avg | numeric | Moy TTFL encaissée vs forwards |
| vs_centers_ttfl_avg | numeric | Moy TTFL encaissée vs centers |
| def_rating | numeric | Rating défensif global |
| updated_at | timestamptz | Dernière MAJ |

### sync_log
| Colonne | Type | Description |
|---------|------|-------------|
| id | serial PK | ID |
| started_at | timestamptz | Début synchro |
| finished_at | timestamptz nullable | Fin synchro |
| status | text | success, error |
| players_updated | integer | Nombre de joueurs mis à jour |
| error_message | text nullable | Message d'erreur si échec |

## Stack technique

### Backend (Python, machine locale)
- **Python 3.12+**
- `nba_api` — stats NBA complètes (game logs, splits, team defense)
- `httpx` — fetch ESPN injuries
- `supabase-py` — client Supabase Python
- `numpy` — calculs de scoring (régression linéaire, écart-type)
- `cron` système ou `schedule` Python — exécution 4x/jour

Structure :
```
sync/
  fetcher.py    — collecte données (nba_api + ESPN)
  scoring.py    — moteur de scoring (6 facteurs + stratégie)
  advisor.py    — génère les argumentaires pro/con/verdict
  main.py       — orchestrateur cron
```

### Frontend (Next.js, Vercel)
- **Next.js 15** (App Router)
- **TypeScript**
- **Tailwind CSS** — styling mobile-first
- `@supabase/supabase-js` — lecture données en temps réel
- `next-pwa` ou `@ducanh2912/next-pwa` — PWA manifest + service worker

Pages :
```
app/
  page.tsx              — Ce soir (accueil)
  player/[id]/page.tsx  — Fiche joueur + verdict
  picks/page.tsx        — Historique picks
  strategy/page.tsx     — Vue stratégique
```

### Hébergement
- **Vercel** (gratuit) — frontend Next.js
- **Supabase** (gratuit, 500 MB) — PostgreSQL + API REST auto
- **Machine locale** — script Python cron

## Planning cron (4x/jour, entre 7h et 00h)

| Heure | Rôle |
|-------|------|
| 07h00 | Résultats de la veille. MAJ `actual_score` dans picks. MAJ standings séries. |
| 12h00 | Schedule du soir confirmé. Premières injury reports. Recos préliminaires. |
| 17h00 | Injury updates finaux (GTD résolus). **Recos définitives du soir.** |
| 22h00 | Late scratches, changements de dernière minute. Update recos si besoin. |
