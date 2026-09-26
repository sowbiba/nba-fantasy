-- 024 — Rappels (spec L2 §3.4). Accès par la clé service uniquement.
create table if not exists push_subscriptions (
  id bigserial primary key,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now(),
  last_ok_at timestamptz
);
alter table push_subscriptions enable row level security;

create table if not exists reminders_sent (
  id bigserial primary key,
  night date not null,
  kind text not null,
  key text not null default '',
  sent_at timestamptz not null default now(),
  unique (night, kind, key)
);
alter table reminders_sent enable row level security;
