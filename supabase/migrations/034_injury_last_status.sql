-- 034 — Dernier statut de blessure daté, conservé quand ESPN retire le
-- joueur de sa liste (le jour de son retour) : sans lui, la période de
-- sécurité de 7 jours (règle « aucun risque ») disparaissait dès son
-- premier match. Idempotente.
--   injury_last_status : dernier statut vu chez ESPN (Out, Day-To-Day, …)
--   injury_last_seen   : dernier jour (Paris) où ESPN listait le joueur
alter table players add column if not exists injury_last_status text;
alter table players add column if not exists injury_last_seen date;

-- Amorce : les joueurs actuellement signalés.
update players set injury_last_status = injury_status, injury_last_seen = current_date
where injury_status is not null and injury_last_seen is null;
