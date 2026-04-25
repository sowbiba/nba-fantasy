-- Allow anon role to delete picks, restricted to rows that haven't been
-- scored yet (actual_score IS NULL). This prevents accidental rewriting of
-- historical stats while still letting the frontend cancel mispicks.
create policy "anon delete unscored picks" on picks
  for delete
  using (actual_score is null);
