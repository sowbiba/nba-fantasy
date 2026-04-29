-- Track every game_id that has been merged into a given matchup
-- aggregate row, so re-running the backfill never double-counts a game.
-- The previous idempotency check only compared `last_game_id`, which
-- protected against re-running the *latest* game but inflated counts
-- for any earlier game seen on a subsequent backfill pass.

alter table matchup_aggregates
  add column if not exists processed_game_ids text[] default '{}';

-- GIN index so the "is this game already counted" check stays cheap as
-- the array grows (long playoff runs accumulate 7+ entries per row).
create index if not exists matchup_aggregates_processed_idx
  on matchup_aggregates using gin (processed_game_ids);
