-- Per-user watchlist of playoff must-plays (solo-user app, no user_id col).
-- Priority 1 = impératif, 2 = forte préférence, 3 = nice-to-have.
create table if not exists player_watchlist (
  player_id integer primary key references players(id),
  priority integer not null check (priority between 1 and 3),
  created_at timestamptz default now()
);

alter table player_watchlist enable row level security;

create policy "anon read watchlist" on player_watchlist
  for select using (true);
create policy "anon insert watchlist" on player_watchlist
  for insert with check (true);
create policy "anon update watchlist" on player_watchlist
  for update using (true);
create policy "anon delete watchlist" on player_watchlist
  for delete using (true);
