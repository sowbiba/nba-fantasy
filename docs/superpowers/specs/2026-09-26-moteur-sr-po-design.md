# Spec — Moteur TTFL unifié saison régulière / playoffs

*Date : 2026-09-26 · Statut : à valider par l'utilisateur · Conception co-construite en session*

## 1. Contexte et objectif

L'application a été retaillée pour les playoffs 2026 (pick-and-drop, séries, save tax). Or la saison régulière 2026-27 commence fin octobre, et **l'app ne la gère pas** : pas de cooldown, picks forcés en `mode='playoffs'`, filtres qui masquent de vrais matchs, projection à 0 en début de saison. Le détail est dans [audit-saison-2026-27.md](../../audit-saison-2026-27.md).

**Objectif** : un moteur dont les règles du jeu, les stats et la stratégie sont séparées, qui **bascule automatiquement entre SR et PO** selon le type de match, et qui bat la référence de **34.0 de moyenne en SR obtenue sans outil**.

**Documents de référence** (font partie de cette spec) :
- [regles-ttfl.md](../../regles-ttfl.md) : règles R1 à R15, la spécification du module `rules/` ;
- [strategie-ttfl.md](../../strategie-ttfl.md) : décisions S1 à S6 (stratégie) et P1-P2 (produit).

**Non-objectifs** :
- jeu en équipe (classements, divisions) ;
- écriture automatique sur trashtalk.co (le pick y est toujours recopié à la main) ;
- DSL ou moteur de règles générique : les règles sont du code Python typé, spécifié par des tests.

## 2. Architecture

Nouveau package `engine/`, qui remplace `sync/`. Dépendances à sens unique : `jobs → strategy → (stats, rules) → io`. `rules` et `stats` ne dépendent pas de Supabase.

```
engine/
  rules/
    availability.py      R3 (cooldown J+30, dans les deux sens, réservations comprises), R15 (Seconde chance), R4, R5, R6
    calendar.py          R8 (fermeture), R11 (soirées éligibles), R12 (play-in), R13 (match fantôme)
    scoring.py           R1 (formule), R10 (x2), R7, R14
    ruleset.py           Ruleset SR / PO ; mode déduit de games.game_type
  stats/
    projection.py        efficacité (TTFL/min) × minutes attendues × facteurs (adversaire, terrain,
                         back-to-back/repos réel, écart de force attendu, tendance)
    priors.py            prior saison précédente fondu (~15 matchs), rôles recalculés sur l'effectif actuel (S6)
    availability_prob.py P(joue) : statut blessure, DNP récents, back-to-back / load management
    elo.py               Elo maison + correction blessures + intersaison (S5, S6)
  strategy/
    planner.py           optimiseur d'affectation joueurs × soirées (commun SR/PO), x2 inclus
    regular.py           horizon glissant 30 j, décote du futur, x2 mensuel (S2, S3)
    playoffs.py          simulation du tableau (centaines de scénarios) + décision robuste (S4)
  explain/               argumentaires et libellés par mode (remplace advisor.py)
  io/                    Supabase, cdn.nba.com, stats.nba.com, ESPN : fetch/push, pagination,
                         limiteurs, retries, disjoncteur (§5). Aucune logique métier.
  jobs/
    daily_sync.py        passage complet (GitHub Actions)
    evening_refresh.py   passage léger du soir : blessures, P(joue), plan
    local_nightly.py     effectifs + matchups défenseur (PC local, stats.nba.com)
    backtest.py          rejoue une saison soir par soir depuis la base
```

### 2.1 Unités et interfaces clés

- `Ruleset.for_night(night) -> Ruleset` : renvoie le jeu de règles SR ou PO du soir.
- `availability.is_available(player_id, night, picks, ruleset) -> Availability(ok, available_from, reason)`.
- `calendar.closing_at(night, games) -> datetime` ; `calendar.eligible(game) -> bool` ; `calendar.is_phantom(game, series) -> bool`.
- `projection.project(player, game, context) -> Projection(mean, stddev)` : pur, ignore le mode.
- `availability_prob.p_play(player, game, context) -> float`.
- `planner.solve(candidates, nights, constraints, x2_months) -> Plan` : maximise la somme des valeurs. Contraintes :
  - une soirée reçoit au plus un pick ;
  - un joueur au plus une fois par fenêtre de cooldown (SR) ou une seule fois (PO) ;
  - les réservations sont fixées ;
  - au plus un x2 par mois.

  Solveur : L1 : `linear_sum_assignment` (horizon = une fenêtre de cooldown). `milp` en L2 pour le x2 mensuel.
- `regular.decide(today) -> Plan` et `playoffs.decide(today) -> Decision` produisent tous deux le pick du soir et le brouillon de deck.

### 2.2 Valeur d'un (joueur, soirée)

- **Espérance complète (S1)** : `V = P(joue) × projection − (1 − P(joue)) × coût_lock`. `coût_lock` = valeur perdue du joueur sur la fenêtre de cooldown (SR) ou sur le reste des PO (PO).
- **Décote du futur (S2)** : pour une soirée à J+k, `V × P(disponible et dans son rôle à J+k)`, décroissante avec k. Paramètres calibrés par backtest.
- **Pénalité de risque x2 (S3)** : un x2 double aussi un score négatif et est perdu si le joueur ne joue pas. Le score retenu pour la soirée x2 est donc `2 × V` corrigé d'une pénalité de variance, pour privilégier un plancher élevé et une P(joue) élevée.
- **PO (S4)** : la valeur future est évaluée par scénario de tableau. Le pick retenu est le candidat qui maximise la moyenne, sur les scénarios, du meilleur total restant.

### 2.3 Code supprimé

Save tax (`TEAM_SAVE_RANKS`, `TEAM_SAVE_TAX_BASE`, `save_tax_for_game`), reservation tax, `personal_strategy.py`, surge G3, bonus watchlist, `seed_personal_strategy.py`, flags désactivés. L'historique git les conserve.

## 3. Modèle de données

Migrations numérotées dans la continuité (017+), toutes **idempotentes**.

| Table | Changements |
|---|---|
| `games` | + `season text`, + `game_type` (`regular`, `cup_final`, `playin`, `playoffs`, `preseason`, `allstar`), déduit du préfixe du `gameId` NBA. La finale NBA Cup est explicitement `cup_final`, éligible. |
| `game_logs` | + `season`, + `team` (équipe au moment du match ; backfill via `is_home` → `games.home_team` / `away_team`) |
| `players` | + `active boolean` (absent des effectifs actuels → non candidat) |
| `series` | + `season` ; clé de série = (season, round, paire) |
| `picks` | + `season`, + `is_x2 boolean default false`. `mode` sans défaut, rempli depuis le match. Statut dérivé : réservé / verrouillé / scoré. `unique(date)` conservé. **Backfill 2025-26** : si `estimated_score = 2 × actual_score`, alors `is_x2 = true` et `estimated_score` est remis à null. |
| `second_chances` (nouvelle) | pick_id (le 0 débloqué), player_id, bought_on, expires_on (= bought_on + 7). Saisie manuelle. Lue par la règle R15. |
| `nights` (nouvelle) | date, season, mode, n_eligible_games, `closing_at`, `is_phantom`. Écrite par le moteur, lue par le front et les rappels. |
| `plan` (remplace `weekly_plan`) | generated_at, night, player_id, is_x2, projection, p_play, value, explanation |
| `team_elo` (nouvelle) | team, date, season, elo |
| `push_subscriptions`, `reminders_sent` (nouvelles) | rappels (§4.3) |
| Archivées | `team_outlook`, `player_team_rank`. `player_watchlist` devient de simples favoris dans l'UI, sans effet sur le moteur. |

**Disponibilité en base** :
- fonction SQL `player_available(player_id, night)` (R3/R4/R5/R6) utilisée par le front ;
- **trigger** sur `picks` qui refuse un pick ou une réservation invalide.

Les versions SQL et Python sont vérifiées par **un fichier de cas partagé** `tests/rules/availability_cases.json`, exécuté contre les deux implémentations.

**Sécurité** : suppression de toutes les policies d'écriture anon (`picks`, `player_watchlist`, `series_forecast`). Les écritures passent par des actions serveur Next.js avec la clé service, derrière **Supabase Auth par code OTP reçu par e-mail et saisi dans la PWA** (un lien magique s'ouvrirait dans Safari, dont le stockage est séparé de la PWA installée sur iOS), limité au seul compte de l'utilisateur (`shouldCreateUser: false`, vérification de l'e-mail dans chaque action serveur). L'anon garde la lecture.

## 4. Jobs et planification

### 4.1 Cadence

| Job | Où | Quand | Contenu |
|---|---|---|---|
| `daily_sync` | GitHub Actions | 07h, 12h, 17h, 22h Paris | calendrier (cdn), box scores de la veille, scores des picks, agrégats, Elo, défense, `nights`, plan |
| `evening_refresh` | GitHub Actions | toutes les heures, 18h → 23h Paris | blessures (ESPN), scoreboard (cdn), P(joue), plan. **Jamais stats.nba.com.** |
| `local_nightly` | cron du PC | 23h50 | effectifs, matchups défenseur (stats.nba.com). Écrit un heartbeat. |
| rappels | pg_cron Supabase → route `/api/reminders` | toutes les 15 min | push à fermeture − 2 h puis − 30 min si aucun pick n'est validé |

Le glissement du cron GitHub (10 à 30 min) est acceptable pour les syncs. Les rappels ont besoin de précision, d'où pg_cron. Le cron local se recale après le passage à l'heure d'hiver.

### 4.2 Réactivation

Syncs réactivés **seulement après** le lot L1, quelques jours avant le premier match : calendrier 2026-27, effectifs forcés en local, priors d'intersaison.

### 4.3 Rappels

- **Web Push de la PWA** (iOS ≥ 16.4) : app installée depuis Safari, manifest `display: standalone`, service worker, permission demandée par un tap sur « Activer les rappels ».
- L'interface `Notifier` a deux implémentations, `WebPushNotifier` et `TelegramNotifier`. Telegram sert de fallback si le push iOS échoue.
- `reminders_sent` garantit l'idempotence.

## 5. Appels aux API (limitation de débit)

Origine historique des blocages : **Akamai devant stats.nba.com** (et dans une moindre mesure cdn.nba.com). Les IP GitHub sont bloquées sur stats.nba.com.

- **Répartition par source** :
  - stats.nba.com → PC local uniquement ;
  - cdn.nba.com → GitHub, avec délai ;
  - ESPN → GitHub, via l'endpoint blessures global déjà utilisé (1 seul appel pour toute la ligue).
- **Couche `io/` commune** :
  - limiteur par hôte (délai minimal configurable, 5 s pour stats.nba.com) ;
  - retry avec backoff exponentiel sur 429, timeout ou réponse vide, en respectant `Retry-After` ;
  - **disjoncteur** : après N échecs consécutifs sur un hôte, arrêt de cet hôte pour le passage ; on garde les données en base et le sync ne plante pas ;
  - pas de re-fetch d'une donnée finale déjà en base ;
  - **budget d'appels par job**, décompte par hôte dans `sync_log`.
- Pagination systématique des lectures Supabase (plafond de 1000 lignes).
- Le backtest ne fait aucun appel externe.

## 6. Front (Next.js)

Écrans (P1) :
- **Ce soir** : reco, espérance, P(joue), « pourquoi ce soir », fermeture, x2, alternatives avec leur date de retour ;
- **Deck 14 jours** : plan et réservations, validation et remplacement, alertes ;
- **Joueur** : « dispo le JJ/MM », meilleurs soirs sur 31 j ;
- **Picks** : historique, moyenne sur toutes les soirées éligibles (sans pick = 0), x2, zéros ;
- **Blessés** ;
- **Matchups**, ramenés à la saison ou à la série en cours ;
- **PO uniquement** : probabilités de titre par équipe, « tes cartes par finaliste ».

Toutes les pages se lisent sur `nights`, `plan` et `player_available`. Aucune règle n'est réimplémentée en TypeScript. Les pages dépendantes du pick passent à `revalidate = 0`. Les dates sont en date US (`todayNBA`), les heures affichées en Europe/Paris.

## 7. Tests et backtest

- `tests/rules/` : chaque règle R1 à R15 avec ses cas limites. `availability_cases.json` est partagé entre Python et SQL. Borne J+30 verrouillée par un test (cas réels 2025-26).
- `tests/stats/` : tendance (sens corrigé : logs du plus récent au plus ancien), priors, back-to-back, repos réel.
- `tests/strategy/` : cas construits à la main, par exemple :
  - « match facile à J+20 → on joue Y ce soir » ;
  - « x2 forcé en fin de mois » ;
  - « PO : joueur d'une équipe condamnée brûlé à temps » ;
  - « option conservée chez chaque finaliste ».
- `tests/io/` : limiteur, retry, disjoncteur, sur API simulées.
- **CI** : pytest ; build et typecheck web ; migrations appliquées sur un Postgres vierge. Python aligné sur la même version en CI et en prod, dépendances pinnées.
- **Backtest** (`jobs/backtest.py`), avec les métriques moyenne par soirée, nombre de zéros et valeur x2 :
  - SR 2025-26 : picks réels (34.0) / best-available / plan 31 j + x2 ;
  - PO 2026 : picks réels / best-available / décision par simulation.

  Stats de match lacunaires avant février 2026 : le backtest SR porte d'abord sur février-avril, avec complément d'historique possible via le PC local (une seule fois).
- **Règle d'activation** : le plan anticipé (SR) et la décision par simulation (PO) ne pilotent la reco du soir que s'ils battent le best-available au backtest. Sinon, la reco du soir reste le best-available (avec l'espérance complète S1), et le plan reste affiché à titre indicatif.

## 8. Livraison

| Lot | Contenu | Échéance |
|---|---|---|
| **L1** | `engine/` (rules, stats, io, planner SR 31 j, S1), migrations §3, trigger et fonction de disponibilité, filtre présaison, priors d'intersaison (S6), `nights`, écrans Ce soir / Deck / Joueur / Picks / Blessés / Matchups, authentification, suppression du code PO mort. **La reco du soir est le best-available avec l'espérance complète (S1). Le plan 31 j est affiché à titre indicatif** tant que le backtest (L2) ne l'a pas validé (§7). Le x2 est saisi manuellement (`is_x2`). | avant le 1er match de SR |
| **L2** | x2 dans le plan (S3), rappels (push + fallback Telegram), `evening_refresh`, backtest SR et activation du plan | novembre (début des x2) |
| **L3** | Elo complet + écart de force dans la projection, simulation du tableau PO (S4), écran PO, backtest PO | avant la mi-avril 2027 |

Chaque lot fait l'objet de son propre plan d'implémentation. Le lot L1 est découpé en trois plans exécutés dans l'ordre : **L1a** données et règles, **L1b** moteur et jobs, **L1c** front et authentification.

## 9. Points à vérifier en cours de route

- **Date du 1er match 2026-27** : le calendrier NBA de la saison dernière n'est plus servi. À charger en début de L1.
- ~~Endpoint blessures ESPN pour toute la ligue~~ : déjà en place (`GLOBAL_INJURIES_URL`).
- ~~Borne du cooldown~~ : **J+30**, vérifiée sur l'historique 2025-26 (6 repicks à 30 jours).
- **Deux zéros 2025-26 contradictoires** (LeBron 06/03, Giannis 08/03, joués selon les logs) : décalage de date ou erreur d'import, à corriger avant le backtest.
- Mise à jour de la CLI Supabase (2.95 → 2.118).
