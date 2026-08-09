# Le moteur TTFL en détail

> Doc interne du moteur de recommandation. Vue d'ensemble : voir le [README](../README.md).

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

