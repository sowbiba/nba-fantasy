-- 023 — Fermeture du deck en base (R8) et mode correction (spec L2 §3.1).

-- Équipe du joueur pour un match : celle de son log si le match est joué
-- (joueur transféré depuis), sinon son équipe actuelle.
create or replace function player_team_for_game(p_player_id int, p_game_id text)
returns text language sql stable as $$
  select coalesce(
    (select l.team from game_logs l where l.player_id = p_player_id and l.game_id = p_game_id limit 1),
    (select team from players where id = p_player_id))
$$;

create or replace function picks_validate() returns trigger
language plpgsql as $$
declare
  g record;
  v_team text;
  a record;
begin
  select * into g from games where id = new.game_id;
  if not found then
    raise exception 'game_not_found' using errcode = 'P0001';
  end if;
  if coalesce(g.game_type, 'unknown') not in ('regular', 'cup_final', 'playoffs') then
    raise exception 'night_not_eligible:%', coalesce(g.game_type, 'unknown') using errcode = 'P0001';
  end if;
  if g.date <> new.date then
    raise exception 'date_mismatch' using errcode = 'P0001';
  end if;
  v_team := player_team_for_game(new.player_id, new.game_id);
  if v_team is distinct from g.home_team and v_team is distinct from g.away_team then
    raise exception 'player_not_in_game' using errcode = 'P0001';
  end if;

  new.mode := case when g.game_type = 'playoffs' then 'playoffs' else 'regular' end;
  new.season := g.season;

  select * into a
  from player_available_on(new.player_id, v_team, new.date, new.season, new.mode, new.id);
  if not a.ok then
    raise exception 'player_unavailable:%', a.reason
      using errcode = 'P0001', detail = coalesce(a.available_from::text, '');
  end if;
  return new;
end
$$;

-- R8 : plus aucun changement de pick une fois la soirée fermée, sauf en
-- mode correction. Les écritures de score (actual_score) passent toujours.
create or replace function picks_closing_guard() returns trigger
language plpgsql as $$
declare
  v_dates date[];
begin
  if current_setting('ttfl.correction', true) = 'on' then
    return coalesce(new, old);
  end if;
  if tg_op = 'INSERT' then
    v_dates := array[new.date];
  elsif tg_op = 'DELETE' then
    v_dates := array[old.date];
  else
    if new.player_id is not distinct from old.player_id
       and new.date is not distinct from old.date
       and new.game_id is not distinct from old.game_id
       and new.is_x2 is not distinct from old.is_x2 then
      return new;
    end if;
    v_dates := array[old.date, new.date];
  end if;
  if exists (select 1 from nights n where n.date = any(v_dates) and now() >= n.closing_at) then
    raise exception 'night_closed' using errcode = 'P0001';
  end if;
  return coalesce(new, old);
end
$$;
drop trigger if exists picks_closing_guard on picks;
create trigger picks_closing_guard before insert or update or delete on picks
  for each row execute function picks_closing_guard();

-- Correction d'une soirée passée (synchro manuelle TrashTalk oubliée).
-- Lève la fermeture pour cette transaction seulement ; cooldown, éligibilité
-- et unicité restent vérifiés par picks_validate et les contraintes.
create or replace function correct_pick(p_date date, p_player_id int) returns void
language plpgsql security definer set search_path = public as $$
declare
  v_game text;
begin
  perform set_config('ttfl.correction', 'on', true);
  if not exists (select 1 from nights n where n.date = p_date and not n.is_phantom and n.n_eligible_games > 0) then
    raise exception 'night_unknown' using errcode = 'P0001';
  end if;
  if p_player_id is null then
    delete from picks where date = p_date;
    return;
  end if;
  select g.id into v_game from games g
  where g.date = p_date and g.game_type in ('regular', 'cup_final', 'playoffs')
    and player_team_for_game(p_player_id, g.id) in (g.home_team, g.away_team)
  limit 1;
  if v_game is null then
    raise exception 'player_not_in_game' using errcode = 'P0001';
  end if;
  if exists (select 1 from picks where date = p_date) then
    update picks set player_id = p_player_id, game_id = v_game, actual_score = null where date = p_date;
  else
    insert into picks (player_id, game_id, date) values (p_player_id, v_game, p_date);
  end if;
end
$$;
revoke execute on function correct_pick(date, int) from public;
revoke execute on function correct_pick(date, int) from anon, authenticated;
grant execute on function correct_pick(date, int) to service_role;
