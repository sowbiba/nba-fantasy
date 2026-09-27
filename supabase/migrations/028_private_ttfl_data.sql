-- 028 — Fin de la lecture publique des données TTFL (spec plan mode
-- public). À appliquer APRÈS le déploiement du front qui lit ces données
-- via le serveur (ownerDb()/requireOwner()), jamais avec la clé anon.
--
-- Retire les policies « anon read » (en réalité lisibles par n'importe quel
-- rôle ayant SELECT sur la table, faute de clause `to`) des tables qui
-- portent des données propres au joueur (picks, plan et son historique de
-- récompenses/forecasts) : plus aucune policy SELECT permissive restante,
-- donc RLS refuse tout le monde sauf un rôle bypassrls (service_role).
-- Restent publics (inchangés) : games, game_logs, players, injuries
-- (colonnes de players), nights, series, matchups, sync_log, standings.
--
-- Idempotente.

drop policy if exists "anon read picks" on picks;
drop policy if exists "anon read recommendations" on recommendations;
drop policy if exists "anon read weekly_plan" on weekly_plan;
drop policy if exists "anon read plan" on plan;
drop policy if exists "anon read second_chances" on second_chances;
drop policy if exists "anon read watchlist" on player_watchlist;
drop policy if exists "anon read forecast" on series_forecast;

-- plan_latest est une vue security_invoker sur plan (021) : elle hérite du
-- retrait ci-dessus sans policy propre.

revoke execute on function period_stats(text, text, date) from public, anon, authenticated;
revoke execute on function player_calendar(int, date, date) from public, anon, authenticated;
grant execute on function period_stats(text, text, date) to service_role;
grant execute on function player_calendar(int, date, date) to service_role;
