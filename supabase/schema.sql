-- supabase/schema.sql

-- Players with aggregated stats
create table players (
  id integer primary key,
  name text not null,
  team text not null,
  position text not null,
  injury_status text,
  injury_detail text,
  avg_ttfl_l5 numeric default 0,
  avg_ttfl_l10 numeric default 0,
  avg_ttfl_l20 numeric default 0,
  avg_ttfl_season numeric default 0,
  stddev_ttfl numeric default 0,
  home_avg numeric default 0,
  away_avg numeric default 0,
  usage_rate numeric default 0,
  updated_at timestamptz default now()
);

-- Playoff series (must be created before games which references it)
create table series (
  id serial primary key,
  round integer not null,
  home_team text not null,
  away_team text not null,
  home_wins integer default 0,
  away_wins integer default 0,
  status text not null default 'active'
);

-- Games schedule
create table games (
  id text primary key,
  date date not null,
  home_team text not null,
  away_team text not null,
  tip_off timestamptz,
  series_id integer references series(id),
  game_number integer,
  status text not null default 'scheduled'
);

-- Individual game box scores
create table game_logs (
  id serial primary key,
  player_id integer not null references players(id),
  game_id text not null references games(id),
  date date not null,
  pts integer default 0,
  reb integer default 0,
  ast integer default 0,
  stl integer default 0,
  blk integer default 0,
  fgm integer default 0,
  fga integer default 0,
  tpm integer default 0,
  tpa integer default 0,
  ftm integer default 0,
  fta integer default 0,
  tov integer default 0,
  minutes integer default 0,
  ttfl_score integer default 0,
  is_home boolean default false,
  unique(player_id, game_id)
);

-- Daily recommendations (top 50)
create table recommendations (
  id serial primary key,
  date date not null,
  player_id integer not null references players(id),
  rank integer not null,
  estimated_score numeric not null,
  perf_score numeric default 0,
  matchup_score numeric default 0,
  strategy_score numeric,
  pros jsonb default '[]',
  cons jsonb default '[]',
  verdict text default '',
  tier text not null,
  tags jsonb default '[]',
  computed_at timestamptz default now(),
  unique(date, player_id)
);

-- User picks
create table picks (
  id serial primary key,
  player_id integer not null references players(id),
  game_id text not null references games(id),
  date date not null,
  mode text not null default 'playoffs',
  estimated_score numeric,
  actual_score integer,
  picked_at timestamptz default now(),
  unique(date)
);

-- Team defensive stats
create table team_defense (
  team text primary key,
  vs_guards_ttfl_avg numeric default 0,
  vs_forwards_ttfl_avg numeric default 0,
  vs_centers_ttfl_avg numeric default 0,
  def_rating numeric default 0,
  updated_at timestamptz default now()
);

-- Sync log
create table sync_log (
  id serial primary key,
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text not null default 'running',
  players_updated integer default 0,
  error_message text
);

-- Indexes for frequent queries
create index idx_recommendations_date on recommendations(date);
create index idx_game_logs_player_date on game_logs(player_id, date desc);
create index idx_games_date on games(date);
create index idx_picks_mode on picks(mode);

-- Enable RLS but allow anon read access
alter table players enable row level security;
alter table games enable row level security;
alter table series enable row level security;
alter table game_logs enable row level security;
alter table recommendations enable row level security;
alter table picks enable row level security;
alter table team_defense enable row level security;
alter table sync_log enable row level security;

-- Read-only policies for anon (frontend)
create policy "anon read players" on players for select using (true);
create policy "anon read games" on games for select using (true);
create policy "anon read series" on series for select using (true);
create policy "anon read game_logs" on game_logs for select using (true);
create policy "anon read recommendations" on recommendations for select using (true);
create policy "anon read picks" on picks for select using (true);
create policy "anon read team_defense" on team_defense for select using (true);
create policy "anon read sync_log" on sync_log for select using (true);

-- Insert policy for picks (frontend can insert picks via anon key)
create policy "anon insert picks" on picks for insert with check (true);

-- Write policies for service role (Python backend uses service role key which bypasses RLS)
-- No explicit policies needed for service role as it bypasses RLS by default
