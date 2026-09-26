# Audit avant la saison régulière 2026-27

*Audit réalisé le 2026-09-26, en lecture seule : moteur Python, front Next.js, infra, DB et CI. Aucun code modifié.*

## TL;DR

L'application a été entièrement retaillée pour les playoffs 2026 (pick-and-drop, séries, élimination, Markov). **La saison régulière n'y existe tout simplement pas** :

- Le **cooldown de 30 jours n'est implémenté nulle part**, ni dans `sync/` ni dans `web/`. `README.md:23` affirme pourtant qu'il l'est.
- Tous les picks sont lus et écrits en `mode='playoffs'`. Résultat : les joueurs pickés en PO 2026 sont exclus **à vie**, et les futurs picks de saison régulière le seraient aussi.
- Plusieurs filtres liés aux playoffs **masqueront de vrais matchs** de saison régulière.

La suite de tests passe (97 tests, `tsc` et `lint` OK), mais **aucun test ne couvre l'orchestration** (`main.py`, `weekly_plan.py`), ni le mode ni le cooldown. De plus, un test existant valide un comportement faux (voir §3, *trend*).

**Verdict refacto** : pas de réécriture. Il faut introduire une **couture « mode de saison »** (détails au §6). La couche projection est largement réutilisable. La couche stratégie est à 100 % playoffs.

---

## 0. Action immédiate (bloquante) : Supabase

Le projet Supabase free-tier est **en pause** (DNS NXDOMAIN depuis début août). Les projets en pause ne sont restaurables que pendant une durée limitée (souvent citée à 90 jours, **à vérifier sur le dashboard**). Si c'est bien 90 jours, l'échéance tombe vers la mi-octobre, avant le match d'ouverture.

→ **Ouvrir le dashboard Supabase et restaurer le projet maintenant.** Ensuite, régénérer `SUPABASE_ACCESS_TOKEN` (401) et appliquer la migration 016.

**Branche « projet non restaurable »** : il faudrait reconstruire depuis le SQL, et **ça ne marche pas en l'état** :
- `002` recrée une policy déjà créée dans `schema.sql:108`. Les `create policy` de 004, 005, 006, 011, 012 et 013 ne sont pas idempotentes.
- `games.home_score` / `away_score` (écrits par `fetcher.py:110`) et `players.injury_short_comment` / `injury_return_date` / `injury_updated_at` (écrits par `main.py:384`) **n'existent dans aucun fichier SQL**.

Dans ce cas, ces points deviennent bloquants.

Une fois la DB revenue, lancer `select mode, count(*) from picks group by mode`. Les 162 picks de saison régulière 2025-26 ont été stockés sous un mode donné, et ce mode détermine l'étendue exacte de l'exclusion erronée actuelle.

---

## 1. Bloquants saison régulière

| # | Problème | Où | Effet |
|---|---|---|---|
| B1 | **Aucun cooldown 30 j** ; exclusion = « jamais pické en PO » | `db.py:97-104`, `main.py:500`, `weekly_plan.py:141,187` ; front : `page.tsx:58`, `player/[id]/page.tsx:64,80`, `strategy/page.tsx:46`, `WatchlistAlerts.tsx:21` | Harper, Shamet, etc. exclus à vie ; aucun joueur « en cooldown » n'est exclu |
| B2 | **Mode `'playoffs'` en dur à l'insert** | `PickButton.tsx:40`, défaut SQL `schema.sql:135` | Chaque pick de saison devient une exclusion définitive |
| B3 | **Filtre « paires de séries terminées » sans borne de saison** | `db.py:134-153`, `weekly_plan.py:170-181`, `page.tsx:72-82`, `strategy/page.tsx:53-67`, `games/page.tsx:29-39` | Tout match de saison entre deux équipes qui se sont affrontées en PO 2026 (~15 paires) **disparaît** : pas de reco, pas de plan, rien dans l'UI |
| B4 | **Pool du plan hebdo = watchlist ∪ `player_team_rank`** | `weekly_plan.py:249` | Ces deux tables sont propres aux playoffs, donc le plan est vide ou absurde en saison |
| B5 | **Cold start : tout le monde projeté à 0** | `scoring.minutes_adjusted_base` (fenêtre 21 j, `scoring.py:95-99`) | En début de saison, le dernier match de chacun date d'avril à juin, donc base = 0 pour tous. Les recos des 1-2 premières semaines sont inutilisables |
| B6 | **Présaison non filtrée** | `load_schedule.py:31-50`, `parse_today_games` (aucun filtre sur le préfixe `gameId` `002`) | Matchs de présaison (`001…`) dans `games`, `game_logs`, les agrégats et les recos |
| B7 | **Saison `"2025-26"` en dur** | `fetcher.py:337,407`, `seed.py:43` ; pas de constante `SEASON` | Fallback de game logs et stats défense sur la mauvaise saison |
| B8 | **Écritures anon publiques sur `picks`** (insert, delete des non-scorés) | `schema.sql:189`, migration 004 ; clé anon dans le bundle | Avec `unique(date)`, un tiers peut bloquer ton pick du soir. Avec un cooldown, il peut aussi « griller » un joueur pour 30 jours |

## 2. Données et rollover de saison

- **Aucune table n'a de colonne `season`.** Tout s'accumule.
- **Agrégats joueurs** : `avg_ttfl_season` est en réalité la moyenne des 40 derniers logs (`main.py:436`, `fetcher.py:454`). Elle traverse la frontière de saison sans le dire (L5/L10/L20 = PO 2026 pour les équipes qualifiées, avril pour les autres).
- **`team_defense`** :
  - calculé sur **tous** les `game_logs`, sans fenêtre de temps (`compute_team_defense.py:30`) ;
  - l'adversaire est déduit de l'équipe **actuelle** du joueur (l.65-70). Après les transferts d'intersaison, un ancien match A vs B d'un joueur passé de A à B est attribué à l'adversaire A, alors que c'était sa propre équipe ;
  - `games` est lu sans pagination (l.44), avec un plafond PostgREST à 1000 lignes pour ~1300 matchs par saison, d'où des logs silencieusement ignorés.
- **Plafond 1000 lignes** ailleurs aussi : `main.py:145` (`matchup_aggregates.processed_game_ids`), `/games` côté front (`PLAYOFFS_START` sans `.limit()`).
- **Joueurs libérés** : l'upsert de roster ne réinitialise jamais `team`, donc un joueur coupé reste candidat avec son ancienne équipe.
- **Rosters** : les IP GitHub sont bloquées par stats.nba.com. Le premier refresh doit tourner en local (`FORCE_ROSTERS=1`). La durée de cache est incohérente : 168 h dans `main.py:313` et `daily-sync.yml`, 72 h dans le commentaire de `config.py:20`.
- **`seed_playoffs`** tourne à chaque sync et associe les séries par (round, paire) sans notion de saison (l.173-210). En avril 2027, une affiche répétée de 2026 retombera sur la ligne `completed` de 2026.
- **`matchup_aggregates` / `box_score_matchups_raw`** : les agrégats `series_id NULL` se cumulent indéfiniment.

## 3. Bugs moteur (vrais en toute saison)

| Bug | Où | Détail |
|---|---|---|
| **Tendance inversée** | `scoring.trend_factor` ; appelants `main.py:543`, `weekly_plan.py:379` | Les logs arrivent du plus récent au plus ancien (`order date desc`), alors que la régression suppose l'ordre inverse. Vérifié : série chaude `[58…40]` (plus récent en premier) → facteur **0.96**, donc un malus. `test_trend_positive` encode la convention inverse et masque le bug. Les séries de 10 logs incluent aussi les DNP à 0 |
| **`days_rest` faux hors « ce soir »** | `weekly_plan.py:384-388`, `future.py` | Le code calcule `(date_match − aujourd'hui)`, pas le repos réel, donc le facteur fatigue est du bruit dans le plan. En saison régulière, les back-to-back et le *load management* sont un vrai signal |
| **Verdict GARDE/JOUE incohérent** | `main.py:894` vs `future.py:47` | Le score du soir est *minutes-adjusted* × probabilité de jouer × DNP. Le score futur est la moyenne brute L5/L10/L20 sans ces facteurs. La comparaison ne porte pas sur la même base |
| **Home/away compté deux fois** | `strategy.compute_strategy_adjustment` | +3 % domicile / −3 % extérieur en plus de `home_away_factor`. Et `series_score=(0,0)` passe `series_tight`, d'où **+2 % sur chaque match à domicile** en saison |
| **Statut du jour écrasé** | `load_schedule.load` | Réécrit `status="scheduled"` sur les matchs du jour, juste après que l'étape 1 a écrit le statut du scoreboard |
| **Docstring vs code** | `config.save_tax_for_game` | Coefficients G4/G5/G6 documentés à 0.80/0.65/0.30, codés à 0.90/0.75/0.40 (inerte actuellement) |
| **N+1 requêtes** | `main.py:436,542`, `weekly_plan.py:373`, `load_schedule` (1 upsert par match) | Acceptable avec 2 à 4 matchs de PO par soir, lourd avec 10 à 15 matchs par soir sur ~450 joueurs |

## 4. Front (`web/`)

- **Aucune logique de cooldown.** Pas de « dispo le JJ/MM », aucun filtrage du Top 3, de `PlayerList` ni de la watchlist. Les dates sont cohérentes (`picks.date = todayNBA()` en ET = `games.date`) : le cooldown se calcule sur ces chaînes de dates, **jamais** en heure de Paris.
- **Textes playoffs en dur** : « Playoffs · Night » (`page.tsx:196`), « DÉJÀ PICKÉ EN PLAYOFFS » (`PickButton.tsx:99`), puces ELIM / SÉRIE CRITIQUE (`RecommendationCard.tsx:288-300`), « sur la série » (`RecommendationCard.tsx:50`).
- **Composants morts en saison** : `WatchlistAlerts` (ne réagit qu'aux tags d'élimination), `SeriesForecastList`, `/series/[id]`, `StrategyBanner` (« ~1j restants » faute de série active, `page.tsx:137-143`).
- **Matchups** indexés `player:opponent` sans `series_id` (`page.tsx:121-133`) : les données de juin ressortiront en novembre.
- **`weekly_plan` non filtré par date** (`strategy/page.tsx:42`) : le plan de juin s'affiche encore.
- **Cache de la page joueur** : `revalidate = 300` (`player/[id]/page.tsx:16`), donc l'état « déjà pické » peut rester faux 5 min. La home, elle, est déjà à 0.
- **Fuseaux** : header de la home sans `timeZone` (`page.tsx:168`, Vercel en UTC), `GamesCollapsible.tsx:24` en *hydration mismatch*.
- **Heuristique x2** `estimated === actual*2` (`PicksTabs.tsx:20-26`) : fragile.
- **Route `/api/live-box-score`** : validation `^\d+$` correcte, mais pas d'authentification ni de rate-limit, et renvoie `e.message`.

## 5. Infra, CI, dépendances

- `requirements.txt` n'a aucun pin (`>=`) et pas de lockfile ; `schedule` est inutilisé, `pytest` est en dépendance de prod.
- Python : CI en 3.14, sync prod en 3.13 (`daily-sync.yml:74`). Les tests ne tournent jamais avec l'interpréteur de prod.
- La CI ne lance que pytest : pas de build ni typecheck web, pas de validation SQL.
- Les noms de migrations (`002_…`) ne sont pas au format de la CLI Supabase. Leur statut d'application n'est connu que par des commentaires.
- Crontab local 23:50 commenté, workflow `daily-sync.yml` désactivé. Réactiver les deux, et recaler le cron après le passage à l'heure d'hiver (25/10).
- Secrets : RAS (`.env` ignoré, absent de l'historique).
- **Synchronisation des picks** : `ttfl-stats/` est un bookmarklet de statistiques autonome et **n'alimente pas** la table `picks`. Les picks n'y entrent que par `PickButton`. Avec un cooldown, un pick oublié en base fait recommander un joueur indisponible pendant 30 jours ; la désynchro avec trashtalk.co est déjà arrivée en mai.

## 6. Recommandation d'architecture

Le code se découpe en deux couches :

1. **Projection** (≈ réutilisable) : `scoring.py`, `fetcher.compute_player_aggregates`, `compute_team_defense`, `injuries.py`, la probabilité de jouer, le risque DNP. Elle a besoin des corrections §2-3 (fenêtre de saison, tendance, repos) et d'une décision sur le cold start (plus bas).
2. **Stratégie** (100 % playoffs) : `strategy.py` (Markov, élimination, réservation, tiers), `personal_strategy.py`, save tax, bonus watchlist d'élimination, surge G3, et **tous les textes de `advisor.py`**. Trois flags sont déjà à OFF, mais tout ce code s'exécute encore à chaque run.

**Proposition : une couture `SeasonMode` avec trois points d'extension**, sans réécriture :

- **(a) Règle de disponibilité** : `regular` = pas de pick sur `[J-29, J]` (à confirmer), `playoffs` = pick-and-drop + équipe éliminée. Une seule implémentation, partagée par le moteur et le front (ou exposée par une vue SQL).
- **(b) Couche stratégie** : `regular` = **best-available sous cooldown** ; `playoffs` = l'existant.
- **(c) Libellés et argumentaires par mode** (advisor + UI), avec masquage des composants séries en saison.

**Ne pas construire d'abord une couche « save / horizon 30 jours » sophistiquée.** Les données 2026 montrent que la save-discipline a coûté ~15 pts/soir (21.1 contre 36.5). La barre à battre est ta moyenne de **34.0 en saison régulière, obtenue sans outil**. Un planificateur 30 jours (Hongrois joueurs × soirs sous contrainte de cooldown, que la machinerie actuelle supporte) pourra venir ensuite, mesuré contre le best-available.

**Mode de saison** : une seule source de vérité (table `settings` ou dérivée des dates via le préfixe `gameId` `002` / `004` / `005`), lue par le sync et le front.

### Décision à prendre : cold start

- **Coupure nette `SEASON_START`** : données propres, mais zéro signal pendant ~2 semaines pour tout le monde (rookies compris).
- **Saison précédente comme *prior* décroissant** : blend `prior 2025-26 × w + saison courante × (1-w)`, avec `w` qui décroît avec le nombre de matchs joués. Utile dès le premier soir, mais biaisé pour les joueurs transférés ou ceux dont le rôle a changé.

La seconde option paraît la plus utile. La fenêtre de 21 jours de `minutes_adjusted_base` doit de toute façon devenir « 21 jours **ou** depuis le début de saison ».

## 7. Règles TTFL (FAQ officielle lue le 2026-09-26)

1. **Cooldown** : deux picks d'un même joueur doivent être espacés d'au moins 30 jours. **Un pick réservé à une date future bloque aussi le joueur**, donc la contrainte s'applique dans les deux sens. La borne exacte (J+30 ou J+31) n'est pas explicite : vérifier sur le deck, ou prendre J+30 exclu par prudence.
2. **DNP, match reporté ou annulé** : 0 point **et** le lock de 30 jours s'applique quand même. La probabilité de jouer est donc centrale dans l'espérance : un pick raté coûte le soir **plus** le joueur pendant 30 jours.
3. **Fermeture du deck** : 00:00 heure de Paris, ou l'heure du **premier match de la soirée** s'il est plus tôt (week-ends, MLK Day : parfois l'après-midi). Les syncs et alertes doivent viser la fermeture, pas le tip-off du joueur. Les injury reports de fin d'après-midi ET tombent souvent **après** une fermeture avancée.
4. **Deck anticipé** : les picks se préparent jusqu'à 2 semaines à l'avance, se modifient jusqu'à la fermeture, mais une date ne peut jamais être vidée. Le moteur doit donc tenir compte des réservations futures, pas seulement des picks passés.
5. **Bonus x2** : de novembre à avril, 1 par mois, perdu s'il n'est pas utilisé. Il double le score, y compris un score négatif, et il est perdu si le joueur ne joue pas. **Non modélisé aujourd'hui** : c'est un problème d'arrêt optimal (poser le x2 sur la meilleure soirée du mois, en profil sûr, avec un seuil qui baisse en fin de mois). À stocker explicitement (`picks.is_x2`) au lieu de l'heuristique `PicksTabs.tsx:20-26`.
6. Les classements hebdomadaires ou mensuels et les divisions ne concernent que le jeu en équipe : aucun impact en solo.
7. Toujours ouvert : la NBA Cup (la FAQ n'en parle pas) et la présaison (non comptée a priori, la FAQ parle de « saison régulière »).

## 8. Priorités

**P0 (avant le 1er match)**
1. Restaurer Supabase, migration 016, nouveau token.
2. `SeasonMode` + cooldown 30 j (moteur **et** front), mode à l'insert (B1, B2).
3. Borner le filtre des séries terminées aux playoffs de la saison courante (B3).
4. Pool du plan en saison = tous les candidats éligibles, pas watchlist ∪ rank (B4).
5. Cold start (B5), filtre présaison (B6), constante `SEASON` (B7).
6. Verrouiller les écritures anon sur `picks` : server action avec clé service, ou Deployment Protection (B8).
7. Fenêtre de saison pour les agrégats et `team_defense`, plus pagination (§2).
8. Tests : `test_weekly_plan`, mode, cooldown, filtre de séries. Corriger le test de tendance.

**P1 (premières semaines)**
- Bugs moteur §3 : tendance, `days_rest`, verdict, double home, statut écrasé.
- Front : libellés par mode, masquage des composants séries, `weekly_plan` filtré par date, `revalidate` de la page joueur, fuseaux.
- Rosters : refresh local, gestion des joueurs libérés, durée de cache unifiée.
- Déclarer les colonnes manquantes, rendre les migrations idempotentes.
- Pins de dépendances, Python 3.13/3.14 aligné, CI avec build web.

**P2 (plus tard)**
- Planificateur 30 jours sous cooldown, à évaluer contre le best-available.
- Clé de série incluant la saison (avant avril 2027).
- Synchro ou contrôle des picks avec trashtalk.co.
- `is_x2` explicite, rate-limit de l'API, dédoublonnage de `todayNBA` / `HARD_OUT_STATUSES`, purge de `sync_log` / `recommendations`.

## 9. Historique saison régulière 2025-26 (table `picks`, analysé le 2026-09-26)

162 picks en `mode='regular'` du 21/10/2025 au 12/04/2026, tous scorés. Moyenne brute **34.0**, médiane 36. Les 2 écarts de 9 jours entre picks d'un même joueur (Mobley, Giannis) viennent du bonus **Seconde chance** (R15), pas d'erreurs d'import : ces zéros sont réels.

- **Import** : `picked_at` = date du pick (import en masse). Pour les picks avec x2, le **score doublé est stocké dans `estimated_score`** (106 = 2 × 53), et `actual_score` reste le score brut. C'est ce que détecte l'heuristique `PicksTabs.tsx:20-26`. À normaliser en `is_x2`.
- **Fuite n°1, les zéros** : **17 picks sur 162 (10,5 %) à 0 ou moins** (16 × 0 et un −6), soit environ 590 pts perdus, **~3,6 pts par soirée**. Plusieurs étaient prévisibles :
  - Cunningham le 02/04 : 0 min sur les 3 matchs précédents ;
  - Curry le 09/04 : back-to-back après 25 min la veille ;
  - Allen le 05/04 : DNP le 31/03.
- **Timing** : quand le joueur a joué, le pick fait **39.3** contre **36.9** de moyenne du joueur sur la saison, soit un timing plutôt bon (+2.4).
- **Soirs sans pick** : 1 à 3 selon la couverture des logs, donc marginal.
- **x2** : 6 sur 6 utilisés (novembre à avril), score brut moyen 39.8 (+6 sur la moyenne), avec un raté à 12 (Mobley, avril).
- **Rotation** : 66 joueurs distincts. Les stars ont été prises 4 à 6 fois, ce qui est proche du plafond permis par le cooldown.
- **Par mois** : oct. 47.7, nov. 33.8, déc. 33.3, **janv. 29.8**, févr. 37.4, mars 32.6, avr. 31.1.
- **Qualité des données** : les `game_logs` de SR sont lacunaires avant février (26 picks sans log). Deux zéros contredisent les logs : LeBron le 06/03 (33 min) et Giannis le 08/03 (27 min). Probable décalage de date (Paris / US) ou score mal saisi à l'import.

**Conclusion** : le levier principal de la SR est d'**éviter les zéros** (disponibilité, back-to-back, retours de blessure), bien avant l'optimisation fine du timing.
