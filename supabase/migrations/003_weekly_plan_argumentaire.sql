-- Add full Pour / Contre / Verdict to weekly_plan entries so that
-- clicking a future-date plan player exposes the same reasoning UX as
-- the top-3 recommendations on the home page.
alter table weekly_plan
  add column if not exists pros jsonb default '[]',
  add column if not exists cons jsonb default '[]',
  add column if not exists verdict text default '';
