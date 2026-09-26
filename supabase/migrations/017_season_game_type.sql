-- 017 — Saison et type de match (R11/R12), équipe du joueur au moment du
-- match, et colonnes présentes en prod mais jamais déclarées (audit §5).
-- Idempotente. Les colonnes dérivées sont remplies par trigger : le sync
-- n'a rien à calculer.

-- Dérive de schéma : colonnes écrites par le sync, absentes des fichiers SQL.
alter table games add column if not exists home_score integer;
alter table games add column if not exists away_score integer;
alter table players add column if not exists injury_short_comment text;
alter table players add column if not exists injury_return_date text;
alter table players add column if not exists injury_updated_at text;

-- Joueur présent dans un effectif actuel (false = coupé / hors NBA).
alter table players add column if not exists active boolean not null default true;

-- Miroir de engine/rules/game_types.py (mêmes cas : tests/rules/game_type_cases.json).
create or replace function game_type_of(p_id text) returns text
language sql immutable as $$
  select case
    when p_id like 'hist\_%' then 'regular'
    when left(p_id, 3) = '001' then 'preseason'
    when left(p_id, 3) = '002' then 'regular'
    when left(p_id, 3) = '003' then 'allstar'
    when left(p_id, 3) = '004' then 'playoffs'
    when left(p_id, 3) = '005' then 'playin'
    when left(p_id, 3) = '006' then 'cup_final'
    else 'unknown'
  end
$$;

create or replace function season_of(p_id text, p_date date) returns text
language sql immutable as $$
  select y::text || '-' || lpad(((y + 1) % 100)::text, 2, '0')
  from (
    select case
      when p_id ~ '^00[1-6][0-9]{2}' then 2000 + substr(p_id, 4, 2)::int
      when extract(month from p_date) >= 9 then extract(year from p_date)::int
      else extract(year from p_date)::int - 1
    end as y
  ) s
$$;

alter table games add column if not exists game_type text;
alter table games add column if not exists season text;
update games set game_type = game_type_of(id), season = season_of(id, date)
where game_type is null or season is null;
create index if not exists idx_games_season_type on games(season, game_type);

create or replace function games_fill_type() returns trigger
language plpgsql as $$
begin
  new.game_type := game_type_of(new.id);
  new.season := season_of(new.id, new.date);
  return new;
end
$$;
drop trigger if exists games_fill_type on games;
create trigger games_fill_type before insert or update of id, date on games
  for each row execute function games_fill_type();

-- Équipe du joueur au moment du match (corrige l'attribution de
-- compute_team_defense après transferts) et saison du log.
alter table game_logs add column if not exists team text;
alter table game_logs add column if not exists season text;
update game_logs gl
set team = coalesce(gl.team, case when gl.is_home then g.home_team else g.away_team end),
    season = coalesce(gl.season, g.season)
from games g
where g.id = gl.game_id and (gl.team is null or gl.season is null);
create index if not exists idx_game_logs_season_team on game_logs(season, team);

create or replace function game_logs_fill() returns trigger
language plpgsql as $$
declare
  v_team text;
  v_season text;
begin
  if new.team is null or new.season is null then
    select case when new.is_home then g.home_team else g.away_team end, g.season
      into v_team, v_season
      from games g where g.id = new.game_id;
    new.team := coalesce(new.team, v_team);
    new.season := coalesce(new.season, v_season);
  end if;
  return new;
end
$$;
drop trigger if exists game_logs_fill on game_logs;
create trigger game_logs_fill before insert or update of game_id, is_home on game_logs
  for each row execute function game_logs_fill();

-- Séries rattachées à leur saison : une affiche de 2027 ne doit plus
-- retomber sur la série « completed » de 2026 (audit §2).
alter table series add column if not exists season text;
update series s set season = sub.season
from (select series_id, min(season) as season from games
      where series_id is not null group by series_id) sub
where sub.series_id = s.id and s.season is null;
-- Séries non rattachées à un match : les seules existantes sont les PO 2026.
update series set season = '2025-26' where season is null;
