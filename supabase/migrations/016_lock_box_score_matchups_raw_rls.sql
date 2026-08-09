-- Drop the blanket anon write policies on box_score_matchups_raw.
--
-- Migration 015 removed the needless anon insert/update/delete policies
-- from team_outlook and player_team_rank but missed this table, created
-- with the same pattern in 013. It is seeded exclusively by the Python
-- backend (service role, bypasses RLS) and only read by the frontend —
-- no UI path writes it. Keep anon read.
--
-- ⚠️ Not yet applied in prod: the Supabase project is paused (offseason,
-- syncs off since 2026-07-07). Apply at reactivation.

drop policy if exists "anon insert box_score_matchups_raw" on box_score_matchups_raw;
drop policy if exists "anon update box_score_matchups_raw" on box_score_matchups_raw;
drop policy if exists "anon delete box_score_matchups_raw" on box_score_matchups_raw;
