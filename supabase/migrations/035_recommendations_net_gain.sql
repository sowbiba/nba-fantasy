-- 035 — Gain net d'un changement du pick du soir (alerte deck du 25/11/2026).
-- Sur la ligne d'un reco qui dépasse le pick du soir de plus de 3 points :
-- points attendus gagnés (ou perdus) sur tout le deck (ce soir + plan) si
-- on le prenait à la place du pick, et l'id du pick comparé (le web ignore
-- le chiffre si le pick a changé depuis le calcul). Idempotente.
-- Pas de clé étrangère vers players : une 2e relation rendrait ambigu
-- l'embed PostgREST `players(name)` des recommandations (PGRST201).

alter table recommendations add column if not exists net_gain numeric;
alter table recommendations add column if not exists net_gain_vs integer;
alter table recommendations drop constraint if exists recommendations_net_gain_vs_fkey;
