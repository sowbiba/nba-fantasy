-- Raw per-pair matchup rows from BoxScoreMatchupsV3, one row per
-- (game, offensive player, defender) triplet. matchup_aggregates is
-- now a derived view of this table — once persisted here, the data
-- can be re-aggregated locally without ever touching NBA again, even
-- if Akamai blocks us or NBA deprecates the endpoint.
--
-- The schema mirrors what fetch_box_score_matchups returns. UNIQUE
-- on (game_id, off_player_id, def_player_id) makes ingestion
-- idempotent: every retry of the same game upserts the same rows.

create table if not exists box_score_matchups_raw (
  id bigserial primary key,
  game_id text not null,
  off_player_id integer not null,
  def_player_id integer not null,
  off_team text,
  def_team text,
  series_id integer references series(id) on delete set null,
  off_player_name text,
  def_player_name text,
  matchup_seconds numeric not null default 0,
  partial_possessions numeric not null default 0,
  player_points integer not null default 0,
  matchup_assists integer not null default 0,
  matchup_turnovers integer not null default 0,
  matchup_blocks integer not null default 0,
  matchup_fgm integer not null default 0,
  matchup_fga integer not null default 0,
  matchup_tpm integer not null default 0,
  matchup_tpa integer not null default 0,
  matchup_ftm integer not null default 0,
  matchup_fta integer not null default 0,
  fetched_at timestamptz default now(),
  unique (game_id, off_player_id, def_player_id)
);

create index if not exists box_score_matchups_raw_game_idx
  on box_score_matchups_raw(game_id);
create index if not exists box_score_matchups_raw_series_idx
  on box_score_matchups_raw(series_id);
create index if not exists box_score_matchups_raw_off_player_idx
  on box_score_matchups_raw(off_player_id);

alter table box_score_matchups_raw enable row level security;

create policy "anon read box_score_matchups_raw"
  on box_score_matchups_raw for select using (true);
create policy "anon insert box_score_matchups_raw"
  on box_score_matchups_raw for insert with check (true);
create policy "anon update box_score_matchups_raw"
  on box_score_matchups_raw for update using (true);
create policy "anon delete box_score_matchups_raw"
  on box_score_matchups_raw for delete using (true);
