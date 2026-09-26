# Réactivation des syncs — début de saison

À dérouler dans l'ordre. Les étapes marquées **(prod)** écrivent dans Supabase.

## Une fois, dès que L1b est mergé

0. **(prod)** Appliquer la migration 020 : `supabase db push --linked` (dry-run d'abord).
   Vérifier : `select job, api_calls from sync_log order by id desc limit 1` fonctionne, et `recommendations` a les colonnes `projection, p_play, value, lock_value, locked_until, best_future`. Sans 020, les deux jobs échouent à leur première écriture.
1. **(prod)** Historique complet 2025-26 (priors S6 + backtest L2), depuis le PC :
   `./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26`
   Vérifier : `select season, count(*) from game_logs group by 1` (≈ 26 000 lignes pour 2025-26).
2. **(prod)** Effectifs 2026-27 à jour : `./venv/bin/python -m engine.jobs.local_nightly`
   Vérifier : `select count(*) from players where active` (≈ 450-530).

## Quand le calendrier 2026-27 est publié

3. **(prod)** Vérifier que `local_nightly` a chargé le calendrier (étape 2). Le calendrier est désormais chargé par le cron local depuis stats.nba.com : 
   `select count(*) from games where season='2026-27'` doit renvoyer >1200 lignes.
   
   Note : `cdn.nba.com` renvoie 403 depuis l'IP locale au 2026-09-26. Le cron local `local_nightly` s'appuie alors sur le calendrier chargé via stats.nba.com; les box scores sont rattrapés chaque nuit par LeagueGameLog (scores des picks à J+1 ou J+2).

4. **(prod)** Un passage de `daily_sync` depuis le PC : `./venv/bin/python -m engine.jobs.daily_sync`
   Vérifier :
   - `select game_type, count(*) from games where season='2026-27' group by 1` : la présaison est en `preseason`, et la **finale NBA Cup en `cup_final`** (préfixe `006`, ex. `0062600001` le 11/12/2026). Sinon : migration de correction du préfixe (voir le plan L1a, tâche 9, step 6).
   - `select * from nights order by date limit 5` : aucune soirée de présaison.

## Quelques jours avant le premier match (après L1c)

5. Activer le workflow : `gh workflow enable daily-sync.yml`.
6. Remplacer la ligne de crontab commentée (`sync.main`, qui n'existe plus) par la ligne `engine.jobs.local_nightly` de `docs/operations.md`.
7. Après le passage à l'heure d'hiver (25/10), vérifier les heures du cron GitHub (commentaire dans `daily-sync.yml`).
