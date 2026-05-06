import { supabase } from "@/lib/supabase";
import { MatchupAggregate, Player, Series } from "@/types";
import BackButton from "../../player/[id]/BackButton";

export const revalidate = 300;

interface PlayerLite extends Pick<Player, "id" | "name" | "team" | "avg_ttfl_season" | "avg_minutes_l10"> {}

type Verdict =
  | "Étouffé"
  | "Tenu"
  | "Neutre"
  | "Productif"
  | "Cuisine"
  | "Bruyant";

function computeVerdict(
  allowedPer36: number,
  seasonPer36: number,
  totalMin: number,
): Verdict {
  if (totalMin < 5) return "Bruyant";
  const expected = Math.max(0, seasonPer36 - 10);
  const delta = allowedPer36 - expected;
  if (delta < -15) return "Étouffé";
  if (delta < -5) return "Tenu";
  if (delta <= 5) return "Neutre";
  if (delta <= 15) return "Productif";
  return "Cuisine";
}

// Colors are from the TTFL-pick perspective (not the defender's): green
// = good pick for the offensive player, red = avoid. Étouffé means the
// player got shut down → red (don't pick). Cuisine means he cooked →
// green (great pick).
const VERDICT_STYLES: Record<Verdict, { bg: string; text: string; border: string }> = {
  "Étouffé": {
    bg: "bg-[color:var(--color-crimson)]/15",
    text: "text-[color:var(--color-crimson)]",
    border: "border-[color:var(--color-crimson)]/40",
  },
  Tenu: {
    bg: "bg-[color:var(--color-flame)]/10",
    text: "text-[color:var(--color-flame)]",
    border: "border-[color:var(--color-flame)]/30",
  },
  Neutre: {
    bg: "bg-white/5",
    text: "text-[color:var(--color-text-soft)]",
    border: "border-white/10",
  },
  Productif: {
    bg: "bg-[color:var(--color-emerald)]/10",
    text: "text-[color:var(--color-emerald)]/85",
    border: "border-[color:var(--color-emerald)]/30",
  },
  Cuisine: {
    bg: "bg-[color:var(--color-emerald)]/20",
    text: "text-[color:var(--color-emerald)]",
    border: "border-[color:var(--color-emerald)]/50",
  },
  Bruyant: {
    bg: "bg-white/5",
    text: "text-[color:var(--color-text-mute)]",
    border: "border-white/10",
  },
};

async function getData(seriesId: number) {
  const [seriesRes, aggRes] = await Promise.all([
    supabase.from("series").select("*").eq("id", seriesId).single(),
    supabase.from("matchup_aggregates").select("*").eq("series_id", seriesId),
  ]);
  const series = (seriesRes.data as Series | null) ?? null;
  if (!series) return { series: null, players: [], aggs: [] };

  const aggs = (aggRes.data || []) as MatchupAggregate[];
  const playerIds = Array.from(new Set(aggs.map((a) => a.player_id)));
  const playersRes = await supabase
    .from("players")
    .select("id, name, team, avg_ttfl_season, avg_minutes_l10")
    .in("id", playerIds);

  return {
    series,
    players: (playersRes.data || []) as PlayerLite[],
    aggs,
  };
}

export default async function SeriesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const seriesId = Number(id);
  const { series, players, aggs } = await getData(seriesId);

  if (!series) {
    return (
      <div className="px-4 py-12 text-center">
        <div className="font-display text-3xl text-[color:var(--color-text-mute)]">
          Série
          <br />
          introuvable
        </div>
      </div>
    );
  }

  const playersById = new Map(players.map((p) => [p.id, p]));
  // Group aggregates by the offensive player's team. Note: matchup row
  // stores `opponent_team` (the team being defended-against), so the
  // offensive player's team is the OTHER team in the series.
  const homeAggs: MatchupAggregate[] = [];
  const awayAggs: MatchupAggregate[] = [];
  for (const a of aggs) {
    const offTeam = a.opponent_team === series.home_team ? series.away_team : series.home_team;
    if (offTeam === series.home_team) homeAggs.push(a);
    else awayAggs.push(a);
  }
  const sortByMinutes = (rows: MatchupAggregate[]) =>
    rows.sort((x, y) => y.matchup_minutes_total - x.matchup_minutes_total);
  sortByMinutes(homeAggs);
  sortByMinutes(awayAggs);

  const playedGames = series.home_wins + series.away_wins;

  return (
    <div className="px-4 py-5 animate-fade-in">
      <BackButton />

      <div className="mt-4 mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-emerald)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-emerald)]" />
          Série · Round {series.round}
        </span>
        <h1 className="font-display text-3xl leading-none tracking-wide text-white mt-1">
          <span className="gold-text">{series.home_team}</span>
          <span className="text-[color:var(--color-flame)] mx-3 font-mono-num">
            {series.home_wins}-{series.away_wins}
          </span>
          <span className="gold-text">{series.away_team}</span>
        </h1>
        <p className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-2">
          {playedGames} match{playedGames > 1 ? "s" : ""} joué{playedGames > 1 ? "s" : ""} · cumulé sur la série
        </p>
      </div>

      <TeamMatchupTable
        team={series.home_team}
        rows={homeAggs}
        playersById={playersById}
      />
      <div className="mt-4">
        <TeamMatchupTable
          team={series.away_team}
          rows={awayAggs}
          playersById={playersById}
        />
      </div>

      <div className="mt-6 px-3 py-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/[0.04] text-[10px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)] leading-relaxed">
        <div className="font-bold text-[color:var(--color-text-soft)] mb-2">Verdicts</div>
        <div className="grid grid-cols-2 gap-1.5 normal-case tracking-normal mb-3">
          <VerdictLegend v="Cuisine" desc="à pick (delta > +15)" />
          <VerdictLegend v="Productif" desc="bon pick (+5 à +15)" />
          <VerdictLegend v="Neutre" desc="à son niveau (±5)" />
          <VerdictLegend v="Tenu" desc="risqué (−5 à −15)" />
          <VerdictLegend v="Étouffé" desc="à fuir (delta < −15)" />
          <VerdictLegend v="Bruyant" desc="< 5 min, sample trop fin" />
        </div>
        <div className="font-bold text-[color:var(--color-text-soft)] mt-3 mb-1">Lecture</div>
        <div className="normal-case tracking-normal">
          <strong>TTFL off./36</strong> = TTFL offensif (PTS+AST+FGM+3PM+FTM −TOV −tirs ratés, sans REB/STL/BLK) que le joueur a produit pendant que ce défenseur principal le couvrait, ramené à 36 min de matchup.
          À comparer au TTFL/36 saison (qui inclut REB/STL/BLK ; ~10 pts de plus en moyenne).
        </div>
      </div>
    </div>
  );
}

function TeamMatchupTable({
  team,
  rows,
  playersById,
}: {
  team: string;
  rows: MatchupAggregate[];
  playersById: Map<number, PlayerLite>;
}) {
  return (
    <section className="relative overflow-hidden rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="h-[3px] w-6 rounded-full bg-[color:var(--color-emerald)]" />
        <h2 className="font-display text-sm tracking-[0.2em] uppercase text-[color:var(--color-emerald)]">
          {team} — défenseurs adverses
        </h2>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-[color:var(--color-text-mute)]">
          Aucune donnée de matchup pour cette série.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((r) => {
            const p = playersById.get(r.player_id);
            const seasonPer36 =
              p && p.avg_minutes_l10 > 0
                ? (p.avg_ttfl_season / p.avg_minutes_l10) * 36
                : 0;
            const p1Min = (r.matchup_minutes_total * r.primary_def_share).toFixed(2);
            const p2Min = (r.matchup_minutes_total * r.secondary_def_share).toFixed(2);
            const p1Pct = Math.round(r.primary_def_share * 100);
            const p2Pct = Math.round(r.secondary_def_share * 100);
            const allowed = r.allowed_off_ttfl_per36;
            const v = computeVerdict(allowed, seasonPer36, r.matchup_minutes_total);
            const vs = VERDICT_STYLES[v];

            return (
              <div
                key={r.player_id}
                className="px-3 py-2.5 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/[0.04]"
              >
                <div className="flex items-baseline justify-between gap-2 mb-1">
                  <span className="font-semibold text-sm text-[color:var(--color-text)] truncate">
                    {p?.name || `#${r.player_id}`}
                  </span>
                  <span
                    className={`text-[9px] font-bold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border shrink-0 ${vs.bg} ${vs.text} ${vs.border}`}
                  >
                    {v}
                  </span>
                </div>
                <div className="text-[10px] text-[color:var(--color-text-mute)] font-mono-num mb-1.5 truncate">
                  {r.samples_count} match{r.samples_count > 1 ? "s" : ""}
                  {" · "}
                  <span className={vs.text}>
                    {allowed > 0 ? "+" : ""}
                    {allowed.toFixed(1)} TTFLoff/36
                  </span>
                  {seasonPer36 > 0 && (
                    <span> (saison {seasonPer36.toFixed(0)})</span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <DefenderCell
                    label="1er"
                    name={r.primary_def_name}
                    minutes={p1Min}
                    pct={p1Pct}
                    primary
                  />
                  <DefenderCell
                    label="2e"
                    name={r.secondary_def_name}
                    minutes={p2Min}
                    pct={p2Pct}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function VerdictLegend({ v, desc }: { v: Verdict; desc: string }) {
  const vs = VERDICT_STYLES[v];
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`text-[8px] font-bold uppercase tracking-[0.15em] px-1.5 py-0.5 rounded-full border shrink-0 ${vs.bg} ${vs.text} ${vs.border}`}
      >
        {v}
      </span>
      <span className="text-[10px] text-[color:var(--color-text-mute)]">{desc}</span>
    </div>
  );
}

function DefenderCell({
  label,
  name,
  minutes,
  pct,
  primary,
}: {
  label: string;
  name: string | null;
  minutes: string;
  pct: number;
  primary?: boolean;
}) {
  return (
    <div
      className={`px-2 py-1.5 rounded-[var(--radius-card-sm)] border ${
        primary
          ? "border-[color:var(--color-gold)]/30 bg-[color:var(--color-gold)]/[0.04]"
          : "border-white/[0.04] bg-white/[0.02]"
      }`}
    >
      <div
        className={`text-[8px] uppercase tracking-[0.22em] font-bold ${
          primary
            ? "text-[color:var(--color-gold)]"
            : "text-[color:var(--color-text-mute)]"
        }`}
      >
        {label} défenseur
      </div>
      <div className="text-[12px] font-semibold text-[color:var(--color-text)] truncate mt-0.5">
        {name || "—"}
      </div>
      <div className="text-[10px] font-mono-num text-[color:var(--color-text-mute)] mt-0.5">
        {minutes} min · {pct}%
      </div>
    </div>
  );
}
