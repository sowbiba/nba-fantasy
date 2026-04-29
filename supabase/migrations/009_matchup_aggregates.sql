-- Per-pair matchup aggregates. One row per (offensive_player, opposing
-- team) inside a given series — captures who actually defends whom and
-- how much they suppress the offensive player's TTFL output.
--
-- The scoring layer reads this to refine matchup_factor, blending the
-- team-positional fallback with the in-series defender's allow rate.
-- Confidence on the pair signal grows with matchup_minutes_total so a
-- thin-sample early game still leans on the team-level number.

create table if not exists matchup_aggregates (
    id                       bigserial primary key,
    player_id                bigint    not null,
    opponent_team            text      not null,
    series_id                bigint,                       -- null = season-wide aggregate
    primary_def_id           bigint,
    primary_def_name         text,
    primary_def_share        numeric default 0,            -- 0..1
    secondary_def_id         bigint,
    secondary_def_name       text,
    secondary_def_share      numeric default 0,
    -- Synthesized "offensive" TTFL produced by the player while the
    -- primary defender was on him, normalized per 36 *matchup* minutes.
    allowed_off_ttfl_per36   numeric default 0,
    allowed_pts_per36        numeric default 0,
    allowed_ast_per36        numeric default 0,
    allowed_to_per36         numeric default 0,
    allowed_blk_against      numeric default 0,            -- counter: blocks BY the def
    allowed_fg_pct           numeric default 0,
    allowed_3p_pct           numeric default 0,
    matchup_minutes_total    numeric default 0,            -- across all defenders
    primary_def_minutes      numeric default 0,            -- only against the top defender
    samples_count            integer default 0,            -- # games contributing
    last_game_id             text,
    updated_at               timestamptz default now()
);

-- Lookup index for the scoring layer
create unique index if not exists matchup_aggregates_unique
    on matchup_aggregates (player_id, opponent_team, coalesce(series_id, 0));

create index if not exists matchup_aggregates_player_idx
    on matchup_aggregates (player_id);
