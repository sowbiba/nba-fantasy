-- 019 — Soirées TTFL (écrites par le moteur, lues par le front et les
-- rappels) et plan du moteur (remplacera weekly_plan en L1b). Idempotente.

create table if not exists nights (
  date date primary key,
  season text not null,
  mode text not null check (mode in ('regular', 'playoffs')),
  n_eligible_games integer not null,
  closing_at timestamptz not null,
  is_phantom boolean not null default false,
  updated_at timestamptz not null default now()
);
alter table nights enable row level security;
drop policy if exists "anon read nights" on nights;
create policy "anon read nights" on nights for select using (true);

create table if not exists plan (
  id bigserial primary key,
  generated_at timestamptz not null default now(),
  night date not null,
  player_id integer not null references players(id),
  is_x2 boolean not null default false,
  projection numeric not null,
  p_play numeric not null,
  value numeric not null,
  explanation text not null default '',
  unique (generated_at, night)
);
create index if not exists idx_plan_generated_night on plan(generated_at desc, night);
alter table plan enable row level security;
drop policy if exists "anon read plan" on plan;
create policy "anon read plan" on plan for select using (true);

-- Disponibilité de tous les joueurs actifs pour une soirée (un appel par page).
create or replace function player_availability(p_night date)
returns table (player_id int, ok boolean, available_from date, reason text)
language sql stable as $$
  select p.id, a.ok, a.available_from, a.reason
  from nights n
  cross join players p
  cross join lateral player_available_on(p.id, p.team, n.date, n.season, n.mode, null) a
  where n.date = p_night and p.active
$$;
