-- Track average minutes played over the last 10 games so the engine can
-- filter out rotation-fringe players whose TTFL averages are misleadingly
-- inflated by garbage-time outliers.
alter table players
  add column if not exists avg_minutes_l10 numeric default 0;
