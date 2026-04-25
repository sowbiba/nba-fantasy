-- Persist the probabilistic discount applied to each weekly_plan pick.
-- 1.0 means the game is certain; lower means the Markov chain on the
-- series state estimates a real chance the game won't be played.
alter table weekly_plan
  add column if not exists pick_probability numeric not null default 1.0;
