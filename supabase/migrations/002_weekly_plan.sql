-- Weekly pick plan — one row per upcoming game day
create table if not exists weekly_plan (
  id serial primary key,
  date date not null,
  player_id integer not null references players(id),
  game_id text not null references games(id),
  estimated_score numeric not null,
  tier text,
  is_home boolean default false,
  opponent text,
  game_number integer,
  elimination text default 'none',
  reasoning text default '',
  generated_at timestamptz default now()
);

create index if not exists idx_weekly_plan_date on weekly_plan(date);

alter table weekly_plan enable row level security;
create policy "anon read weekly_plan" on weekly_plan for select using (true);
