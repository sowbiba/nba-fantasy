-- 030 — Elo maison des équipes et prédictions de match (L3a, spec
-- 2026-09-28-l3a-elo-design.md §1/§3). Données du mode connecté
-- uniquement : RLS activée, aucune policy (donc aucune lecture anon /
-- authenticated, comme picks/plan depuis 028) ; seul service_role
-- (BYPASSRLS) lit et écrit, via daily_sync. Idempotente.

create table if not exists team_elo (
  team text primary key,
  rating numeric not null,
  games int not null default 0,
  updated_at timestamptz not null default now()
);
alter table team_elo enable row level security;

create table if not exists game_predictions (
  game_id text primary key references games(id) on delete cascade,
  home_rating numeric not null,
  away_rating numeric not null,
  home_win_prob numeric not null check (home_win_prob between 0 and 1),
  expected_margin numeric not null,
  updated_at timestamptz not null default now()
);
alter table game_predictions enable row level security;
