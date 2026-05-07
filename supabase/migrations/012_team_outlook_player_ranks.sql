-- Personal-strategy layer: per-team outlook (advance/eliminate/tossup) and
-- per-player save rank inside that team. The engine blends these with the
-- existing performance/strategy scores so the recommendations follow the
-- user's view of the bracket while still adapting to in-game signals
-- (DNP risk, hot streak, elimination pressure).
--
-- Read flow:
--   sync/main.py loads both tables, joins them per scored player, and
--   calls sync.personal_strategy.compute_multiplier(...) to produce a
--   multiplier in [0.4, 1.3] applied to estimated_score.

create table if not exists team_outlook (
  team text primary key,
  outlook text not null check (outlook in ('advance', 'eliminate', 'tossup')),
  -- When true and outlook='eliminate': nudge top-ranked players towards
  -- home games (mild penalty on away, mild boost on home). For other
  -- outlooks the flag is ignored.
  home_save_top boolean not null default true,
  notes text,
  updated_at timestamptz default now()
);

create table if not exists player_team_rank (
  player_id integer primary key references players(id) on delete cascade,
  team text not null,
  -- 1 = highest save priority (kept for the deepest round we expect to
  -- reach with this team). Higher numbers = burned earlier. NULL is not
  -- allowed; players we don't care about simply aren't in the table.
  save_rank integer not null check (save_rank between 1 and 12),
  notes text,
  updated_at timestamptz default now()
);

create index if not exists player_team_rank_team_idx on player_team_rank(team);

alter table team_outlook enable row level security;
alter table player_team_rank enable row level security;

create policy "anon read team_outlook" on team_outlook for select using (true);
create policy "anon insert team_outlook" on team_outlook for insert with check (true);
create policy "anon update team_outlook" on team_outlook for update using (true);
create policy "anon delete team_outlook" on team_outlook for delete using (true);

create policy "anon read player_team_rank" on player_team_rank for select using (true);
create policy "anon insert player_team_rank" on player_team_rank for insert with check (true);
create policy "anon update player_team_rank" on player_team_rank for update using (true);
create policy "anon delete player_team_rank" on player_team_rank for delete using (true);
