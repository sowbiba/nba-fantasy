-- 022 — Fin des écritures anon (spec §3). Les écritures passent par les
-- actions serveur du front (session propriétaire + clé service). À appliquer
-- APRÈS le déploiement du front L1c. La lecture anon est conservée.
-- Idempotente.

drop policy if exists "anon insert picks" on picks;
drop policy if exists "anon delete unscored picks" on picks;
drop policy if exists "anon insert watchlist" on player_watchlist;
drop policy if exists "anon update watchlist" on player_watchlist;
drop policy if exists "anon delete watchlist" on player_watchlist;
drop policy if exists "anon insert forecast" on series_forecast;
drop policy if exists "anon update forecast" on series_forecast;
drop policy if exists "anon delete forecast" on series_forecast;
