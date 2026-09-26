-- 020 — Sorties du moteur L1b : espérance complète (S1) sur les
-- recommandations du soir, et journal des jobs (daily_sync / local_nightly)
-- avec le décompte des appels API par hôte. Idempotente.

alter table recommendations add column if not exists projection numeric;
alter table recommendations add column if not exists p_play numeric;
alter table recommendations add column if not exists value numeric;
alter table recommendations add column if not exists lock_value numeric;
alter table recommendations add column if not exists locked_until date;
alter table recommendations add column if not exists best_future text;

alter table sync_log add column if not exists job text not null default 'daily_sync';
alter table sync_log add column if not exists api_calls jsonb not null default '{}'::jsonb;
create index if not exists idx_sync_log_job_started on sync_log(job, started_at desc);
