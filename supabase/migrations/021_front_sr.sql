-- 021 — Lectures du front saison régulière (aucune règle TTFL côté TS) et
-- garde-fous x2 en base (R10). Ajouts uniquement : à appliquer AVANT le
-- déploiement du nouveau front. Idempotente.

-- Dernier plan généré par le moteur (le front ne filtre plus en TS).
create or replace view plan_latest with (security_invoker = true) as
select p.* from plan p
where p.generated_at = (select max(generated_at) from plan);

-- Soirées où l'équipe du joueur joue, avec sa disponibilité (R3/R4/R5/R15).
create or replace function player_calendar(p_player_id int, p_from date, p_to date)
returns table (night date, closing_at timestamptz, game_id text, opponent text,
               is_home boolean, ok boolean, available_from date, reason text)
language sql stable as $$
  select n.date, n.closing_at, g.id,
         case when g.home_team = p.team then g.away_team else g.home_team end,
         g.home_team = p.team, a.ok, a.available_from, a.reason
  from players p
  join nights n on n.date between p_from and p_to
                and not n.is_phantom and n.n_eligible_games > 0
  join games g on g.date = n.date and p.team in (g.home_team, g.away_team)
              and g.game_type in ('regular', 'cup_final', 'playoffs')
  cross join lateral player_available_on(p.id, p.team, n.date, n.season, n.mode, null) a
  where p.id = p_player_id
  order by n.date
$$;

-- Statistiques d'une période (R14 : soirée éligible sans pick = 0 ; pick pas
-- encore scoré = exclu). Miroir de engine.rules.scoring.period_average.
create or replace function period_stats(p_season text, p_mode text, p_until date)
returns table (nights int, scored_nights int, total int, average numeric,
               picks int, zeros int, x2_used int)
language sql stable as $$
  with n as (
    select date from nights
    where season = p_season and mode = p_mode and date < p_until
      and not is_phantom and n_eligible_games > 0
  ), pts as (
    select case
             when p.id is null then 0
             when p.actual_score is null then null
             else p.actual_score * (case when p.is_x2 then 2 else 1 end)
           end as points
    from n left join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
  )
  select (select count(*) from n)::int,
         count(points)::int,
         coalesce(sum(points), 0)::int,
         case when count(points) > 0 then round(avg(points)::numeric, 1) end,
         (select count(*) from picks where season = p_season and mode = p_mode and date < p_until)::int,
         (select count(*) from picks where season = p_season and mode = p_mode and date < p_until and actual_score = 0)::int,
         (select count(*) from picks where season = p_season and mode = p_mode and is_x2)::int
  from pts
$$;

-- Matchups défenseur ↔ attaquant ramenés à la saison (données brutes L1b).
create or replace view matchup_season with (security_invoker = true) as
select r.off_player_id as player_id, r.def_team as opponent_team, g.season,
       r.def_player_id, max(r.def_player_name) as def_player_name,
       round(sum(r.matchup_seconds) / 60.0)::int as minutes,
       sum(r.player_points)::int as points,
       count(distinct r.game_id)::int as games
from box_score_matchups_raw r
join games g on g.id = r.game_id
group by r.off_player_id, r.def_team, g.season, r.def_player_id;

-- R10 : un x2 par mois, en saison régulière, de novembre à avril.
create unique index if not exists picks_x2_month
  on picks (season, (extract(year from date)), (extract(month from date)))
  where is_x2;
alter table picks drop constraint if exists picks_x2_window;
alter table picks add constraint picks_x2_window
  check (not is_x2 or (mode = 'regular' and extract(month from date) in (11, 12, 1, 2, 3, 4)));
