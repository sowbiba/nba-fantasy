-- User pronostics per playoff series. Used as a blend input by the strategy
-- layer (60% seed default, 40% user forecast, with the forecast weight
-- fading out as actual games are played).
create table if not exists series_forecast (
  series_id integer primary key references series(id) on delete cascade,
  winner_team text not null,
  expected_games integer not null check (expected_games between 4 and 7),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table series_forecast enable row level security;

drop policy if exists "anon read forecast" on series_forecast;
create policy "anon read forecast" on series_forecast
  for select using (true);
drop policy if exists "anon insert forecast" on series_forecast;
create policy "anon insert forecast" on series_forecast
  for insert with check (true);
drop policy if exists "anon update forecast" on series_forecast;
create policy "anon update forecast" on series_forecast
  for update using (true);
drop policy if exists "anon delete forecast" on series_forecast;
create policy "anon delete forecast" on series_forecast
  for delete using (true);
