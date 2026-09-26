# Réactivation des syncs — début de saison

À dérouler dans l'ordre. Les étapes marquées **(prod)** écrivent dans Supabase.

## Une fois, dès que L1b est mergé

1. **(prod)** Historique complet 2025-26 (priors S6 + backtest L2), depuis le PC :
   `./venv/bin/python -m engine.jobs.local_nightly --backfill-season 2025-26`
   Vérifier : `select season, count(*) from game_logs group by 1` (≈ 26 000 lignes pour 2025-26).
2. **(prod)** Effectifs 2026-27 à jour : `./venv/bin/python -m engine.jobs.local_nightly`
   Vérifier : `select count(*) from players where active` (≈ 450-530).

## Quand le calendrier 2026-27 est publié

3. **(prod)** Un passage de `daily_sync` depuis le PC : `./venv/bin/python -m engine.jobs.daily_sync`
   Vérifier :
   - `select game_type, count(*) from games where season='2026-27' group by 1` : la présaison est en `preseason`, et la **finale NBA Cup en `cup_final`** (préfixe `006`). Sinon : migration de correction du préfixe (voir le plan L1a, tâche 9, step 6).
   - `select * from nights order by date limit 5` : aucune soirée de présaison.

## Quelques jours avant le premier match (après L1c)

4. Activer le workflow : `gh workflow enable daily-sync.yml`.
5. Décommenter la ligne de crontab `engine.jobs.local_nightly` (commande dans `docs/operations.md`).
6. Après le passage à l'heure d'hiver (25/10), vérifier les heures du cron GitHub (commentaire dans `daily-sync.yml`).
