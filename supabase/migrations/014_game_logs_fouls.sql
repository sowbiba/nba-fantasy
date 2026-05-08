-- Personal fouls per player per game. Surfaced in the game-detail
-- live box score so we can spot foul-trouble nights at a glance —
-- TTFL relevant because 5+ fouls usually means reduced minutes for
-- the rest of the game.
alter table game_logs
  add column if not exists fouls integer default 0;
