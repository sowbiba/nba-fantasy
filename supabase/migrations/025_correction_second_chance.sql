-- 025 — Correction et seconde chance (M8, revue finale L2a).
--
-- Une "Seconde chance" (table `second_chances`, migration 018) est achetée
-- sur un pick à 0 : `player_available_on` la retrouve par `pick_id` pour
-- lever le cooldown de ce joueur. Si `correct_pick` remplace le joueur
-- d'un pick existant (synchro manuelle oubliée), la ligne reste attachée à
-- l'ancien `pick_id` : elle waive alors le cooldown du *nouveau* joueur (pas
-- celui qui l'a réellement achetée) et pointe un `player_id` obsolète. Une
-- seconde chance appartient au joueur qui l'a payée, mis à zéro : quand ce
-- joueur est remplacé, elle n'a plus de sens et doit disparaître avec lui.
create or replace function correct_pick(p_date date, p_player_id int) returns void
language plpgsql security definer set search_path = public as $$
declare
  v_game text;
  v_pick_id int;
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
  select id into v_pick_id from picks where date = p_date;
  if v_pick_id is not null then
    -- On remplace le joueur : la seconde chance de ce pick (achetée par
    -- l'ancien joueur mis à zéro) ne suit pas — elle disparaît avec lui.
    delete from second_chances where pick_id = v_pick_id;
    update picks set player_id = p_player_id, game_id = v_game, actual_score = null where id = v_pick_id;
  else
    insert into picks (player_id, game_id, date) values (p_player_id, v_game, p_date);
  end if;
end
$$;
revoke execute on function correct_pick(date, int) from public;
revoke execute on function correct_pick(date, int) from anon, authenticated;
grant execute on function correct_pick(date, int) to service_role;
