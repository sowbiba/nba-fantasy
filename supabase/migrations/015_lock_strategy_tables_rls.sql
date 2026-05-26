-- Lock down the personal-strategy tables (team_outlook, player_team_rank).
--
-- These are seeded by the Python backend (service role, which bypasses RLS)
-- and only READ by the frontend — no UI path writes them. The blanket
-- anon insert/update/delete policies from migration 012 are therefore
-- needless write surface on the public anon key. Drop them; keep anon read.
--
-- NB: player_watchlist and series_forecast intentionally KEEP their anon
-- write policies — the UI legitimately edits them (WatchlistStar toggles
-- watchlist rows, SeriesForecastList upserts forecasts).

drop policy if exists "anon insert team_outlook" on team_outlook;
drop policy if exists "anon update team_outlook" on team_outlook;
drop policy if exists "anon delete team_outlook" on team_outlook;

drop policy if exists "anon insert player_team_rank" on player_team_rank;
drop policy if exists "anon update player_team_rank" on player_team_rank;
drop policy if exists "anon delete player_team_rank" on player_team_rank;
