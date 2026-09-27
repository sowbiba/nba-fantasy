-- À exécuter UNE fois en prod (tâche 10 du plan L2a), après avoir créé le
-- secret dans Vault :  select vault.create_secret('<valeur>', 'reminders_secret');
-- (valeur = REMINDERS_SECRET de Vercel ; ne jamais la committer).
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.unschedule('ttfl-reminders')
where exists (select 1 from cron.job where jobname = 'ttfl-reminders');

select cron.schedule('ttfl-reminders', '*/15 * * * *', $$
  select net.http_post(
    url := 'https://ttfl-advisor.vercel.app/api/reminders',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'reminders_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 30000
  )
$$);
