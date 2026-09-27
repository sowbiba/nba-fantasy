-- 027 — Classement Est/Ouest calculé depuis les matchs (spec plan mode
-- public). Vue publique : hérite de la lecture anon de `games` via
-- security_invoker. Saison régulière uniquement (`game_type = 'regular'`,
-- `status = 'final'`) ; la finale de la NBA Cup (`cup_final`) et le
-- préseason (`preseason`) sont exclus. Saison affichée = la plus récente
-- présente dans `games` avec `game_type = 'regular'`. Idempotente.

create or replace view standings with (security_invoker = true) as
with target_season as (
  select max(season) as season from games where game_type = 'regular'
),
conferences (team, conference) as (
  values
    ('ATL', 'Est'), ('BOS', 'Est'), ('BKN', 'Est'), ('CHA', 'Est'), ('CHI', 'Est'),
    ('CLE', 'Est'), ('DET', 'Est'), ('IND', 'Est'), ('MIA', 'Est'), ('MIL', 'Est'),
    ('NYK', 'Est'), ('ORL', 'Est'), ('PHI', 'Est'), ('TOR', 'Est'), ('WAS', 'Est'),
    ('DAL', 'Ouest'), ('DEN', 'Ouest'), ('GSW', 'Ouest'), ('HOU', 'Ouest'), ('LAC', 'Ouest'),
    ('LAL', 'Ouest'), ('MEM', 'Ouest'), ('MIN', 'Ouest'), ('NOP', 'Ouest'), ('OKC', 'Ouest'),
    ('PHX', 'Ouest'), ('POR', 'Ouest'), ('SAC', 'Ouest'), ('SAS', 'Ouest'), ('UTA', 'Ouest')
),
results as (
  select
    tg.team,
    c.conference,
    g.id as game_id,
    g.date,
    tg.is_home,
    case when tg.is_home then g.home_score > g.away_score
         else g.away_score > g.home_score end as won
  from games g
  cross join lateral (values (g.home_team, true), (g.away_team, false)) as tg(team, is_home)
  join conferences c on c.team = tg.team
  join target_season ts on g.season = ts.season
  where g.game_type = 'regular' and g.status = 'final'
),
totals as (
  select
    team,
    count(*) filter (where won) as wins,
    count(*) filter (where not won) as losses,
    count(*) filter (where is_home and won) as home_wins,
    count(*) filter (where is_home and not won) as home_losses,
    count(*) filter (where not is_home and won) as away_wins,
    count(*) filter (where not is_home and not won) as away_losses
  from results
  group by team
),
ranked_games as (
  select *,
    row_number() over (partition by team order by date desc, game_id desc) as rn
  from results
),
last10 as (
  select
    team,
    count(*) filter (where won) as last10_wins,
    count(*) filter (where not won) as last10_losses
  from ranked_games
  where rn <= 10
  group by team
),
with_prev as (
  select
    team,
    date,
    game_id,
    won,
    lag(won) over (partition by team order by date desc, game_id desc) as prev_won
  from ranked_games
),
streak_groups as (
  select
    team,
    won,
    sum(case when won is distinct from prev_won then 1 else 0 end)
      over (partition by team order by date desc, game_id desc) as grp
  from with_prev
),
streaks as (
  select team, won, count(*) as n
  from streak_groups
  where grp = 1
  group by team, won
),
base as (
  select
    c.team,
    c.conference,
    coalesce(t.wins, 0) as wins,
    coalesce(t.losses, 0) as losses,
    coalesce(t.home_wins, 0) as home_wins,
    coalesce(t.home_losses, 0) as home_losses,
    coalesce(t.away_wins, 0) as away_wins,
    coalesce(t.away_losses, 0) as away_losses,
    coalesce(l.last10_wins, 0) as last10_wins,
    coalesce(l.last10_losses, 0) as last10_losses,
    coalesce((case when s.won then 'V' else 'D' end) || s.n, '') as streak
  from conferences c
  left join totals t on t.team = c.team
  left join last10 l on l.team = c.team
  left join streaks s on s.team = c.team
),
ranked_base as (
  select
    b.*,
    coalesce(round(b.wins::numeric / nullif(b.wins + b.losses, 0), 3), 0) as pct,
    row_number() over (
      partition by b.conference
      order by coalesce(round(b.wins::numeric / nullif(b.wins + b.losses, 0), 3), 0) desc,
                b.wins desc, b.team asc
    ) as rank
  from base b
),
leaders as (
  select conference, wins as leader_wins, losses as leader_losses
  from ranked_base
  where rank = 1
)
select
  (select season from target_season) as season,
  rb.conference,
  rb.team,
  rb.wins,
  rb.losses,
  rb.pct,
  ((ld.leader_wins - rb.wins) + (rb.losses - ld.leader_losses))::numeric / 2 as games_behind,
  rb.home_wins,
  rb.home_losses,
  rb.away_wins,
  rb.away_losses,
  rb.last10_wins,
  rb.last10_losses,
  rb.streak,
  rb.rank
from ranked_base rb
join leaders ld on ld.conference = rb.conference
order by rb.conference, rb.rank;

grant select on standings to anon, authenticated;
