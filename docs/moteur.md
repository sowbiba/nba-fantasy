# Le moteur TTFL en détail

> Doc interne du moteur de recommandation. Vue d'ensemble : voir le [README](../README.md). Conception d'ensemble : [spec moteur SR/PO](superpowers/specs/2026-09-26-moteur-sr-po-design.md).

## Formule TTFL officielle (pour référence)

```
TTFL = (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM)
     - (TOV + FG_miss + 3P_miss + FT_miss)
```

Implémentée par `compute_ttfl_score` dans `engine/rules/scoring.py` (R1). Le même module porte le bonus x2 (`night_points`, R10) et la moyenne sur les soirées éligibles, où une soirée sans pick compte 0 (`period_average`, R14).

## Projection d'un match (`engine/stats/`)

La projection d'un joueur pour un match est **efficacité récente × minutes de rôle attendues × facteurs de contexte** (`engine/stats/projection.py::project`) :

```
projection = profile.base × opp_factor × terrain × fatigue
profile.base = ttfl_per_min × exp_minutes
terrain = 1.02 (domicile) / 0.98 (extérieur)      # HOME_FACTOR / AWAY_FACTOR
fatigue = 0.96 si 2e soir d'un back-to-back sinon 1.0   # B2B_FACTOR
```

### Le profil joueur (`engine/stats/profile.py`)

`build_profile` calcule, sur les matchs **joués** uniquement (l'absence est portée par P(joue), jamais par la projection, pour éviter le double compte) :

- **`ttfl_per_min`** : efficacité pondérée par récence (poids `0.9^i`, `RECENCY`) sur les 15 derniers matchs joués (`EFFICIENCY_GAMES`) ;
- **`exp_minutes`** : minutes de rôle, même pondération, sur les 8 derniers matchs joués (`ROLE_GAMES`) ;
- un **prior saison précédente fondu** (S6) : à `PRIOR_K = 10` matchs joués cette saison, le prior et la saison en cours pèsent autant (`n / (n + PRIOR_K)`). Sans historique du tout (rookie), fallback `ROOKIE_TTFL_PER_MIN = 0.55` et `ROOKIE_MINUTES = 12.0` ;
- le prior de minutes est mis à l'échelle de l'effectif actuel par `role_scales` (une équipe qui a perdu sa star redistribue les minutes, un effectif encombré les partage), borné à `[0.85, 1.15]` (`ROLE_SCALE_BOUNDS`) ;
- **`stddev`** (régularité) sur les 20 derniers scores TTFL disponibles ;
- **`availability_rate`** : taux de présence sur les 15 derniers logs (tous, DNP inclus), borné à `[0.5, 1.0]` (`PRESENCE_BOUNDS`), défaut `0.9` sans historique.

### Facteur défensif adverse (`engine/stats/team_defense.py`)

`defense_factors` calcule, par équipe et par poste (`G`/`F`/`C`), le TTFL/minute concédé rapporté à la moyenne de la ligue, à partir de `game_logs.team` (équipe au moment du match, pas l'équipe actuelle — corrige l'attribution après transferts). La saison en cours est fondue avec la saison précédente régressée de moitié vers 1.0 (`PRIOR_REGRESSION = 0.5`, `PRIOR_GAMES = 15`), borné à `[0.85, 1.15]` (`FACTOR_BOUNDS`).

### P(joue) (`engine/stats/availability_prob.py`)

- **Statut ESPN** (`play_probability`) :

  | Statut ESPN | P(joue) |
  |-------------|---------|
  | `Out`, `Out For Season`, `Suspended` | 0.00 (exclu du pool, `HARD_OUT_STATUSES`) |
  | `Doubtful` | 0.20 (exclu du pool) |
  | `Questionable`, `Game-Time Decision` | 0.55 |
  | `Day-To-Day` | 0.65 |
  | `Probable` | 0.85 |
  | autre / absent | 1.00 |

- **Facteur de risque DNP** (`dnp_risk_factor`) : ESPN étant en retard sur les mises à l'écart, un joueur à 0 minute sur ses derniers matchs est déprécié (×0.30 si 3 DNP sur les 3 derniers, ×0.55 si 2, ×0.75–0.90 si 1) — multiplicatif avec le statut.
- **Repos de back-to-back** (`B2B_REST_FACTOR = 0.93`) : appliqué aux gros minutages (`exp_minutes ≥ 30`, `B2B_REST_MIN_MINUTES`) au 2e soir d'un back-to-back.
- Pour une soirée future (`future_p_play`), le statut du jour ne dit presque rien d'un match dans plusieurs jours (sauf saison terminée) : on retient le **taux de présence récent** (`availability_rate` du profil) plutôt que le statut ESPN.

## Espérance complète et décote du futur (`engine/strategy/value.py`, S1/S2)

Picker un joueur le bloque 30 jours (R3), qu'il joue ou non (R7). L'espérance d'un pick tient compte de ce risque :

```
tonight_value = P(joue) × projection − (1 − P(joue)) × lock_value
lock_value    = meilleure espérance future du joueur dans la fenêtre de cooldown,
                décotée de FUTURE_DECAY = 0.985 par jour d'avance
future_value  = décote(k) × P(joue) × projection   # pour une soirée à k jours
```

`FUTURE_DECAY` est un paramètre à calibrer par backtest (L2, non encore fait).

## Plan 30 jours (`engine/strategy/planner.py`, `engine/strategy/regular.py`, S2)

Le plan sur l'horizon glissant de **30 jours** (`HORIZON_DAYS`, une fenêtre de cooldown R3) est un problème d'affectation résolu par l'**algorithme hongrois** (`scipy.optimize.linear_sum_assignment`, dans `planner.solve`) : une soirée reçoit au plus un pick, chaque joueur au plus une fois sur la fenêtre, réservations (picks déjà posés) fixées, la soirée du jour forcée si un candidat existe.

`regular.decide` assemble tout : profils, projections, P(joue), disponibilité (R3/R4/R5/R6/R15), filtre `MIN_EXP_MINUTES = 15.0` (sous ce seuil de minutes de rôle attendues, pas candidat), et produit :
- la **reco du soir** (`recommendations`, top `TOP_RECOMMENDATIONS = 50`) triée par `tonight_value`, avec pour chaque candidat sa `lock_value`, la date de déblocage et son meilleur match futur connu ;
- le **plan indicatif** (`plan`) sur toute la fenêtre.

> ⚠️ **La reco du soir en L1 est le best-available (S1), pas le plan anticipé.** Le plan reste affiché à titre indicatif tant qu'il n'a pas battu le best-available au backtest (règle d'activation, spec §7, lot L2).

## Ce qui a été supprimé dans le refacto L1b

Ces mécanismes de l'ancien moteur (`sync/`) n'existent plus. Le détail de la suppression (raison, données) est dans la [spec moteur SR/PO §2.3](superpowers/specs/2026-09-26-moteur-sr-po-design.md#23-code-supprimé).

- **Couche stratégie playoffs** (tiers Elite/Solide/Filler par rang relatif au soir, usage boost coéquipier blessé, détection du risque d'élimination, bonus/malus domicile-extérieur et match d'élimination, décision burn-or-save à 7 jours) : retirée. La disponibilité en playoffs (pick-and-drop, éliminations) passe désormais par les mêmes règles `engine.rules.availability`/`regular.decide` que la saison régulière ; une stratégie PO dédiée (simulation du tableau, S4) est prévue pour le lot L3.
- **Réservation des elites pour les tours avancés** (pénalité de réservation par tour/seed) et **couche stratégie personnelle** (save tax par équipe/rang) : les données de la saison 2026 ont montré que la discipline de save faisait chuter la moyenne (21.1 vs 36.5 en best-available). Le moteur suit désormais l'espérance projetée pure (S1/S2 ci-dessus).
- **Facteur de tendance récente** (régression linéaire sur L10) : le sens était inversé (audit) et redondant avec la pondération de récence du profil (`RECENCY` dans `engine/stats/profile.py`) ; retiré, pas remplacé.
- **Split domicile/extérieur individuel** : remplacé par un effet terrain fixe (`HOME_FACTOR`/`AWAY_FACTOR` dans `engine/stats/projection.py`) — le split individuel était trop bruité et comptait déjà dans l'effet terrain global.
- **Plan hebdomadaire par algorithme hongrois sur 7 jours avec x2 mensuel** (`sync/weekly_plan.py`) : remplacé par le plan 30 jours ci-dessus (`engine/strategy/planner.py`). Le x2 mensuel dans le plan (S3) est prévu pour le lot L2 ; en attendant, `is_x2` est saisi manuellement.
- **Cap L5** (`L5_CAP_MINUTES`/`L5_CAP_RATIO`) : la pondération L5/L10/L20 elle-même a disparu avec le passage à l'efficacité pondérée par récence (`profile.py`) — plus de fenêtre L5 isolée à capper.

## Tuning des paramètres

Les constantes ci-dessus vivent directement dans le code, pas dans un fichier de config central :

| Paramètre | Où | Rôle |
|---|---|---|
| `RECENCY`, `EFFICIENCY_GAMES`, `ROLE_GAMES`, `PRIOR_K`, `ROLE_SCALE_BOUNDS`, `PRESENCE_BOUNDS` | `engine/stats/profile.py` | Pondération de récence et fonte du prior saison précédente |
| `HOME_FACTOR`, `AWAY_FACTOR`, `B2B_FACTOR` | `engine/stats/projection.py` | Effet terrain et fatigue |
| `FACTOR_BOUNDS`, `PRIOR_REGRESSION`, `PRIOR_GAMES` | `engine/stats/team_defense.py` | Bornes et fonte du facteur défensif adverse |
| `INJURY_PLAY_PROBABILITY`, `HARD_OUT_STATUSES`, `B2B_REST_FACTOR`, `B2B_REST_MIN_MINUTES` | `engine/stats/availability_prob.py` | P(joue) |
| `FUTURE_DECAY` | `engine/strategy/value.py` | Décote du futur (S2) |
| `HORIZON_DAYS`, `MIN_EXP_MINUTES`, `TOP_RECOMMENDATIONS` | `engine/strategy/regular.py` | Fenêtre du plan, seuil de minutes candidat, taille de la reco du soir |
| `TOP_PER_NIGHT` | `engine/strategy/planner.py` | Candidats gardés par soirée dans la matrice hongroise |

Aucun de ces paramètres n'a encore été calibré par backtest (lot L2) : ce sont des valeurs de départ, à date d'écriture de ce document.
