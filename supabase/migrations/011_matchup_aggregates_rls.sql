-- Enable anon read on matchup_aggregates so the web app's /series/[id]
-- page can render. The table was created without RLS policies, which
-- meant supabase blocked all reads from the anon key (RLS implicitly
-- enabled on creation in newer Supabase projects). Writes stay
-- service-key only — the daily sync runs with the service role.

alter table matchup_aggregates enable row level security;

create policy "anon read matchup_aggregates"
  on matchup_aggregates
  for select using (true);
