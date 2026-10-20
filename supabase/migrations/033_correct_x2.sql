-- 033 — Correction du x2 d'une soirée passée (x2 posé sur trashtalk.co mais
-- pas déclaré dans l'app avant la fermeture). Même principe que
-- correct_pick (023/025) : lève la fermeture pour cette transaction
-- seulement ; unicité mensuelle (picks_x2_month) et fenêtre novembre-avril
-- (picks_x2_window) restent garanties par les contraintes.
create or replace function correct_x2(p_date date, p_value boolean) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform set_config('ttfl.correction', 'on', true);
  update picks set is_x2 = p_value where date = p_date;
  if not found then
    raise exception 'no_pick' using errcode = 'P0001';
  end if;
end
$$;
revoke execute on function correct_x2(date, boolean) from public;
revoke execute on function correct_x2(date, boolean) from anon, authenticated;
grant execute on function correct_x2(date, boolean) to service_role;
