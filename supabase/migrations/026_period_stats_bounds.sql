-- 026 — period_stats : picks/zeros/x2_used bornés à p_until et restreints
-- aux soirées éligibles (nights non fantômes, n_eligible_games > 0). Avant
-- ce correctif les trois compteurs lisaient picks directement : un pick sur
-- une date hors nights (ou hors saison éligible) était compté, et x2_used
-- ignorait p_until (un x2 réservé dans le futur était déjà compté comme
-- "utilisé"). Idempotente.

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
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode)::int,
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
            where p.actual_score = 0)::int,
         (select count(*) from n join picks p on p.date = n.date and p.season = p_season and p.mode = p_mode
            where p.is_x2)::int
  from pts
$$;
