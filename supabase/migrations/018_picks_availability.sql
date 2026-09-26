-- 018 — Picks : saison, x2 explicite, bonus Seconde chance, et règle de
-- disponibilité (R3/R4/R5/R6/R15) appliquée en base par trigger.
-- Miroir de engine/rules/availability.py : mêmes cas dans
-- tests/rules/availability_cases.json. Idempotente.

create or replace function cooldown_days() returns int
language sql immutable as $$ select 30 $$;  -- R3 : pické à J → disponible à J+30

alter table picks add column if not exists season text;
alter table picks add column if not exists is_x2 boolean not null default false;
alter table picks alter column mode drop default;  -- déduit du match par le trigger
create index if not exists idx_picks_player_season on picks(player_id, season, mode, date);

update picks p set season = season_of(p.game_id, p.date) where p.season is null;

-- Réconciliation historique de picks.mode : l'ancien front codait en dur
-- mode='playoffs' et l'ancienne colonne avait ce défaut, donc des picks SR
-- historiques peuvent porter mode='playoffs'. Le backfill x2 et les règles
-- de disponibilité en dépendent. Ne déclenche pas picks_validate (qui ne se
-- déclenche que sur player_id/date/game_id).
update picks p set mode = case when g.game_type = 'playoffs' then 'playoffs' else 'regular' end
from games g where g.id = p.game_id
  and p.mode is distinct from (case when g.game_type = 'playoffs' then 'playoffs' else 'regular' end);

-- Backfill x2 2025-26 : l'import stockait le score doublé dans estimated_score.
-- actual_score <> 0 : sinon les zéros (0 = 2 × 0) passeraient pour des x2.
-- Restreint à l'import SR 2025-26 : un pick PO dont l'estimation (float du
-- moteur) vaut par coïncidence 2 × le score réel ne doit pas être touché.
update picks set is_x2 = true, estimated_score = null
where not is_x2 and actual_score is not null and actual_score <> 0
  and estimated_score = 2 * actual_score
  and mode = 'regular' and season = '2025-26';

-- R15 — bonus Seconde chance, saisi à la main à l'achat.
create table if not exists second_chances (
  id serial primary key,
  pick_id integer not null references picks(id) on delete cascade,
  player_id integer not null references players(id),
  bought_on date not null,
  expires_on date not null,
  unique (pick_id)
);
alter table second_chances enable row level security;
drop policy if exists "anon read second_chances" on second_chances;
create policy "anon read second_chances" on second_chances for select using (true);

-- Seconde chance utilisées en 2025-26 (boutique : achats du 17/11 et du 13/03).
insert into second_chances (pick_id, player_id, bought_on, expires_on)
select p.id, p.player_id, b.bought_on, b.bought_on + 7
from (values (date '2025-11-12', date '2025-11-17'),
             (date '2026-03-08', date '2026-03-13')) as b(pick_date, bought_on)
join picks p on p.date = b.pick_date and p.actual_score = 0
on conflict (pick_id) do nothing;

create or replace function player_available_on(
  p_player_id int,
  p_team text,
  p_night date,
  p_season text,
  p_mode text,
  p_exclude_pick_id int default null
) returns table (ok boolean, available_from date, reason text)
language plpgsql stable as $$
declare
  v_cd int := cooldown_days();
  v_prev date;
  v_next date;
begin
  if p_mode = 'playoffs' then
    -- R4 : pick-and-drop sur toute la période PO de la saison.
    if exists (
      select 1 from picks q
      where q.player_id = p_player_id and q.season = p_season and q.mode = 'playoffs'
        and q.id is distinct from p_exclude_pick_id
    ) then
      return query select false, null::date, 'playoffs_used'::text; return;
    end if;
    -- R5 : seules les équipes du 1er tour sont qualifiées (play-in éliminé).
    if exists (select 1 from series s where s.season = p_season and s.round = 1)
       and not exists (
         select 1 from series s
         where s.season = p_season and s.round = 1
           and p_team in (s.home_team, s.away_team)
       ) then
      return query select false, null::date, 'not_qualified'::text; return;
    end if;
    -- R5 : perdant d'une série terminée.
    if exists (
      select 1 from series s
      where s.season = p_season and s.status = 'completed'
        and ((s.home_team = p_team and s.home_wins < 4)
          or (s.away_team = p_team and s.away_wins < 4))
    ) then
      return query select false, null::date, 'team_eliminated'::text; return;
    end if;
    return query select true, null::date, null::text; return;
  end if;

  -- R3 : cooldown de v_cd jours dans les deux sens, hors pick débloqué par
  -- une Seconde chance active ce soir-là (R15).
  select max(q.date) into v_prev
  from picks q
  where q.player_id = p_player_id and q.season = p_season and q.mode = 'regular'
    and q.id is distinct from p_exclude_pick_id
    and q.date <= p_night and p_night - q.date < v_cd
    and not exists (
      select 1 from second_chances sc
      where sc.pick_id = q.id and p_night between sc.bought_on and sc.expires_on
    );
  if v_prev is not null then
    return query select false, v_prev + v_cd, 'cooldown'::text; return;
  end if;

  select min(q.date) into v_next
  from picks q
  where q.player_id = p_player_id and q.season = p_season and q.mode = 'regular'
    and q.id is distinct from p_exclude_pick_id
    and q.date > p_night and q.date - p_night < v_cd
    and not exists (
      select 1 from second_chances sc
      where sc.pick_id = q.id and p_night between sc.bought_on and sc.expires_on
    );
  if v_next is not null then
    return query select false, null::date, 'reserved_nearby'::text; return;
  end if;

  return query select true, null::date, null::text;
end
$$;

-- Validation d'un pick ou d'une réservation. Ne se déclenche que si le
-- joueur, la date ou le match changent : les mises à jour de score ou de x2
-- faites par le sync ne sont jamais revalidées.
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
  select team into v_team from players where id = new.player_id;
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
drop trigger if exists picks_validate on picks;
create trigger picks_validate before insert or update of player_id, date, game_id on picks
  for each row execute function picks_validate();
