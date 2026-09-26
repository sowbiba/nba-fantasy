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

### Zoom sur la base de projection

Depuis `MINUTES_ADJUSTED_BASE = True` (`sync/config.py`), la base n'est plus la moyenne brute mais **l'efficacité récente (TTFL/min) × les minutes attendues** (pondérées par récence, DNP inclus). Ça corrige deux angles morts : un titulaire redescendu en minutes de banc quand un coéquipier revient, et un joueur qui sort de l'infirmerie (projeté ≈ 0 au lieu de porter sa forme d'avant-blessure). Voir `scoring.minutes_adjusted_base` ; mettre le flag à `False` restaure la moyenne pondérée classique, qui reste le fallback quand les données minutes manquent :

- **L5** = moyenne TTFL des 5 derniers matchs (forme ultra-récente)
- **L10** = moyenne des 10 derniers
- **L20** = moyenne des 20 derniers

Poids : `L5 × 3 + L10 × 2 + L20 × 1`, divisé par 6 — L5 domine (50 %), L10 renforce (33 %), L20 ancre (17 %).

Exemple Jokic : L5=58, L10=55, L20=52 → `(58×3 + 55×2 + 52×1) / 6 = 56.0`

### Garde-fous candidats

- `MIN_MINUTES_L10 = 15` : sous 15 min de moyenne sur les 10 derniers matchs, le joueur n'est pas candidat (le signal est dominé par le garbage time)
- **Cap L5** (`L5_CAP_MINUTES = 20`, `L5_CAP_RATIO = 1.5`) : pour un joueur hors rotation, un L5 > 1.5× sa moyenne saison est presque toujours un artefact de blowouts (pattern Carlson/Sandfort) → capé. Les titulaires ne sont jamais touchés
- `MIN_SPLIT_GAMES = 4` : en dessous de 4 matchs, le split home/away est du bruit → fallback neutre sur la moyenne saison

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

Les statuts durs excluent du pool (`HARD_OUT_STATUSES`) ; les statuts incertains multiplient le score estimé par une **probabilité de jouer** (`INJURY_PLAY_PROBABILITY`, `sync/config.py`) pour raisonner en espérance :

| Statut ESPN | Impact |
|-------------|--------|
| `Out`, `Out For Season`, `Suspended`, `Doubtful` | Exclu du classement |
| `Questionable` | Flag ⚠️ + score × 0.55 |
| `Game-Time Decision` | Flag 🔶 + score × 0.55 |
| `Day-To-Day` | Flag 🔶 + score × 0.65 |
| `Probable` | score × 0.85 |

S'y ajoute un **facteur de risque DNP** (`dnp_risk_factor`) : ESPN étant en retard sur les mises à l'écart, un joueur à 0 minute sur ses derniers matchs est déprécié (×0.30 si 3 DNP sur 3, ×0.55 si 2, ×0.75–0.90 si 1) — multiplicatif avec la probabilité de jouer.

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

> ⚠️ **Couche désactivée depuis le 2026-05-26** (`MAX_RESERVATION_PENALTY = 0.0`) : les données de la saison 2026 ont montré que la discipline de save faisait chuter la moyenne (21.1 vs 36.5 en best-available). Le moteur suit désormais le score projeté pur ; le mécanisme reste en place et se réactive en remontant le plafond.

Le principe : sans cette couche, l'algo hongrois brûlerait facilement Jokic au Game 2 du Round 1, alors que DEN a 3 tours potentiels devant lui.

**Pénalité de réservation** :
```
reservation = min(MAX, player_elite_factor × team_potential × round_factor × MAX)
final_score = perf_score × (1 − reservation)
```

Où (constantes dans `sync/strategy.py`) :

| Composante | Formule |
|------------|---------|
| `player_elite_factor` | `min(1.0, (avg_season − 28) / 12)` — 28 = starter moyen, 40+ = elite max |
| `team_potential` | 1.0 pour tête de série R1 (home court), 0.5 pour seed 5-8, 0.3 pour play-in |
| `round_factor` | 1.0 en R1, 0.55 en R2, 0.2 en R3 (Conf Finals), 0.0 en Finales |
| `MAX_RESERVATION_PENALTY` | **0.0 actuellement** (était 0.60 → plafond à -60 %) |

**L'élimination critique annule toujours la réservation** — si son équipe peut être out ce soir, le moteur le recommandera quand même.

Une **couche stratégie personnelle** (save tax par équipe/rang, `sync/personal_strategy.py` + `TEAM_SAVE_RANKS`/`TEAM_SAVE_TAX_BASE` dans `config.py`) est également désactivée (`ENABLE_PERSONAL_STRATEGY = False`), pour la même raison.

### Réglage

Les constantes clés sont dans `sync/strategy.py` :

```python
MAX_RESERVATION_PENALTY = 0.0   # 0 = best-available ; remonter (ex: 0.45-0.60) pour réactiver la réservation
ROUND_RESERVATION_FACTOR = {1: 1.0, 2: 0.55, 3: 0.2, 4: 0.0}
TEAM_POTENTIAL_TOP_SEED = 1.0
TEAM_POTENTIAL_LOW_SEED = 0.5
TEAM_POTENTIAL_UNKNOWN = 0.3
```

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

### Réservation elites

Voir [la section Réservation](#réservation-des-elites-pour-les-tours-avancés) : désactivée (`MAX_RESERVATION_PENALTY = 0.0` dans `sync/strategy.py`), remonter le plafond pour la réactiver.

### Seuils "joueur éligible"

`sync/weekly_plan.py`, dans `build_candidates` :
```python
if season_avg < 10:
    continue
```

Ce seuil filtre les joueurs qui n'ont quasiment pas joué pour garder la matrice Hungarian raisonnable. Le baisser à 5 inclut plus de role players obscurs. S'y ajoutent le seuil de minutes (`MIN_MINUTES_L10 = 15`) et le cap L5 (`L5_CAP_MINUTES` / `L5_CAP_RATIO`) de `sync/config.py` — voir [Garde-fous candidats](#garde-fous-candidats).

