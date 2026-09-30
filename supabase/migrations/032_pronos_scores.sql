-- 032 — Pronos 2026-27 (table privée `season_pronos`, RLS sans policy,
-- lecture/écriture réservées au serveur via la clé service) et vue publique
-- `player_ttfl_season` (page « Scores TTFL ») agrégée depuis `game_logs` +
-- `games`. Idempotente.

-- season_pronos : un prono par (season, name_key) — name_key = nom
-- normalisé (casse/espaces) côté serveur, pas ici. `token_hash` = SHA-256
-- du jeton d'auteur (jamais le jeton en clair). `updated_at` maintenu par
-- trigger (pas par les server actions) : toute mise à jour, quelle que
-- soit son origine, reste datée correctement.
create table if not exists season_pronos (
  id uuid primary key default gen_random_uuid(),
  season text not null,
  name text not null,
  name_key text not null,
  wins jsonb not null default '{}',
  token_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (season, name_key)
);

alter table season_pronos enable row level security;
-- Aucune policy : RLS sans policy permissive refuse anon/authenticated ;
-- seul service_role (bypassrls) lit/écrit, via les server actions.

create or replace function season_pronos_set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end
$$;

drop trigger if exists season_pronos_set_updated_at on season_pronos;
create trigger season_pronos_set_updated_at before update on season_pronos
  for each row execute function season_pronos_set_updated_at();

-- player_ttfl_season : vue publique (page « Scores TTFL »), agrégée par
-- (season, game_type, player). `minutes > 0` exclut les DNP ; le join à
-- `games` restreint aux types saison régulière / playoffs (playin,
-- preseason, cup_final, allstar exclus). `team` = l'équipe du joueur lors
-- de son dernier match de la période (dernier par date, puis game_id en
-- cas d'égalité) — couvre les transferts en cours de saison. `top_score` =
-- son meilleur match (ttfl_score desc), égalité tranchée par la date la
-- plus ancienne puis game_id.
drop view if exists player_ttfl_season;

create view player_ttfl_season with (security_invoker = true) as
with logs as (
  select
    g.season,
    g.game_type,
    gl.player_id,
    gl.game_id,
    gl.date,
    gl.team,
    gl.ttfl_score,
    case when gl.team = g.home_team then g.away_team else g.home_team end as opponent
  from game_logs gl
  join games g on g.id = gl.game_id
  where gl.minutes > 0 and g.game_type in ('regular', 'playoffs')
),
agg as (
  select
    season,
    game_type,
    player_id,
    count(*) as games,
    sum(ttfl_score) as total_ttfl,
    round(avg(ttfl_score)::numeric, 1) as avg_ttfl
  from logs
  group by season, game_type, player_id
),
last_team as (
  select season, game_type, player_id, team
  from (
    select
      season, game_type, player_id, team,
      row_number() over (
        partition by season, game_type, player_id
        order by date desc, game_id desc
      ) as rn
    from logs
  ) ranked
  where rn = 1
),
top_game as (
  select season, game_type, player_id, ttfl_score as top_score, date as top_date, opponent as top_opponent
  from (
    select
      season, game_type, player_id, ttfl_score, date, opponent,
      row_number() over (
        partition by season, game_type, player_id
        order by ttfl_score desc, date asc, game_id asc
      ) as rn
    from logs
  ) ranked
  where rn = 1
)
select
  a.season,
  a.game_type,
  a.player_id,
  p.name,
  lt.team,
  a.games,
  a.avg_ttfl,
  a.total_ttfl,
  tg.top_score,
  tg.top_date,
  tg.top_opponent
from agg a
join players p on p.id = a.player_id
join last_team lt
  on lt.season = a.season and lt.game_type = a.game_type and lt.player_id = a.player_id
join top_game tg
  on tg.season = a.season and tg.game_type = a.game_type and tg.player_id = a.player_id;

grant select on player_ttfl_season to anon, authenticated;
