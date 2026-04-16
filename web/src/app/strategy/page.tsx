import { supabase } from "@/lib/supabase";
import { Recommendation, Series, Game, WeeklyPlanEntry, Player } from "@/types";
import Link from "next/link";
import { todayParis } from "@/lib/date";

export const revalidate = 300;

async function getData() {
  const today = todayParis();
  const futureDate = new Date();
  futureDate.setDate(futureDate.getDate() + 7);
  const futureDateStr = futureDate.toISOString().split("T")[0];

  const [recsRes, seriesRes, gamesRes, planRes, playersRes] = await Promise.all([
    supabase.from("recommendations").select("*").eq("date", today),
    supabase.from("series").select("*").eq("status", "active"),
    supabase
      .from("games")
      .select("*")
      .gte("date", today)
      .lte("date", futureDateStr)
      .order("date"),
    supabase.from("weekly_plan").select("*").order("date"),
    supabase.from("players").select("id, name, team, position"),
  ]);

  return {
    recs: (recsRes.data || []) as Recommendation[],
    series: (seriesRes.data || []) as Series[],
    games: (gamesRes.data || []) as Game[],
    plan: (planRes.data || []) as WeeklyPlanEntry[],
    players: (playersRes.data || []) as Pick<Player, "id" | "name" | "team" | "position">[],
  };
}

export default async function StrategyPage() {
  const { recs, series, games, plan, players } = await getData();
  const playersMap = new Map(players.map((p) => [p.id, p]));

  const elites = recs.filter((r) => r.tier === "elite").length;
  const solids = recs.filter((r) => r.tier === "solid").length;
  const fillers = recs.filter((r) => r.tier === "filler").length;

  const planTotal = plan.reduce((sum, e) => sum + e.estimated_score, 0);
  const today = todayParis();

  const gamesByDate = new Map<string, Game[]>();
  for (const g of games) {
    const list = gamesByDate.get(g.date) || [];
    list.push(g);
    gamesByDate.set(g.date, list);
  }

  let bestDate = "";
  let bestCount = 0;
  for (const [date, dateGames] of gamesByDate) {
    if (dateGames.length > bestCount) {
      bestCount = dateGames.length;
      bestDate = date;
    }
  }

  return (
    <div className="px-4 py-5 animate-fade-in">
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-gold)]" />
          Vue d&apos;ensemble
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          <span className="gold-text">STRATÉGIE</span>
        </h1>
      </div>

      {/* --------------- capital --------------- */}
      <Section title="Capital restant" accent="gold">
        <div className="grid grid-cols-3 gap-2">
          <CapitalTile
            value={elites}
            label="Elite"
            stars="★★★"
            color="text-[color:var(--color-gold)]"
            borderColor="border-[color:var(--color-gold)]/30"
            bgColor="bg-[color:var(--color-gold)]/5"
          />
          <CapitalTile
            value={solids}
            label="Solide"
            stars="★★"
            color="text-[color:var(--color-ice)]"
            borderColor="border-[color:var(--color-ice)]/30"
            bgColor="bg-[color:var(--color-ice)]/5"
          />
          <CapitalTile
            value={fillers}
            label="Filler"
            stars="★"
            color="text-[color:var(--color-text-soft)]"
            borderColor="border-white/10"
            bgColor="bg-white/[0.02]"
          />
        </div>
      </Section>

      {/* --------------- weekly plan --------------- */}
      <Section
        title={`Plan de la semaine · ${planTotal.toFixed(0)} pts estimés`}
        accent="gold"
        className="mt-4"
      >
        {plan.length === 0 ? (
          <p className="text-sm text-[color:var(--color-text-mute)]">
            Aucun plan disponible. Le prochain sync en génèrera un.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {plan.map((entry) => {
              const player = playersMap.get(entry.player_id);
              const d = new Date(entry.date + "T12:00:00");
              const dayLabel = d
                .toLocaleDateString("fr-FR", {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                })
                .replace(".", "");
              const isToday = entry.date === today;
              const isElim = entry.elimination === "critical";
              return (
                <Link
                  key={entry.id}
                  href={`/player/${entry.player_id}`}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/[0.04] hover:border-[color:var(--color-gold)]/30 transition-colors"
                >
                  <div className="w-16 shrink-0">
                    <div
                      className={`text-[10px] uppercase tracking-[0.15em] font-bold ${
                        isToday
                          ? "text-[color:var(--color-flame)]"
                          : "text-[color:var(--color-text-soft)]"
                      }`}
                    >
                      {isToday ? "Auj." : dayLabel}
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-semibold text-sm text-[color:var(--color-text)] truncate">
                        {player?.name || "?"}
                      </span>
                      {isElim && (
                        <span className="text-[8px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded bg-[color:var(--color-crimson)]/15 text-[color:var(--color-crimson)] border border-[color:var(--color-crimson)]/30 animate-pulse-red">
                          ELIM
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-[color:var(--color-text-mute)] mt-0.5 truncate">
                      {player?.team}{" "}
                      {entry.is_home ? "vs" : "@"} {entry.opponent}
                      {entry.game_number ? (
                        <span className="text-[color:var(--color-gold)]/80 ml-1">
                          · G{entry.game_number}
                        </span>
                      ) : null}
                      {entry.is_home ? " · 🏠" : " · ✈"}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-display text-xl leading-none font-mono-num gold-text">
                      {entry.estimated_score.toFixed(1)}
                    </div>
                    <div className="text-[8px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-0.5">
                      Estimé
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
        <p className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-3 leading-relaxed">
          Optimisation Hungarian — affecte 1 joueur par jour sur 7 jours en
          maximisant le score total. Recalculé à chaque sync.
        </p>
      </Section>

      {/* --------------- calendar 7 days --------------- */}
      <Section title="Prochains 7 jours" accent="violet" className="mt-4">
        {gamesByDate.size === 0 ? (
          <p className="text-sm text-[color:var(--color-text-mute)]">
            Aucun match prévu
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            {Array.from(gamesByDate.entries()).map(([dateStr, dateGames]) => {
              const d = new Date(dateStr + "T12:00:00");
              const dayLabel = d
                .toLocaleDateString("fr-FR", {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                })
                .replace(".", "");
              const isBest = dateStr === bestDate;
              const isToday = dateStr === today;
              const count = dateGames.length;
              // intensity 0..1 for bar width
              const intensity = Math.min(count / 8, 1);
              return (
                <div
                  key={dateStr}
                  className="flex items-center gap-3 py-2 border-b border-white/[0.04] last:border-0"
                >
                  <div className="w-20 shrink-0">
                    <div
                      className={`text-[11px] uppercase tracking-[0.15em] font-bold ${
                        isToday
                          ? "text-[color:var(--color-flame)]"
                          : "text-[color:var(--color-text-soft)]"
                      }`}
                    >
                      {isToday ? "Aujourd'hui" : dayLabel}
                    </div>
                  </div>
                  <div className="flex-1 relative h-2 bg-white/[0.04] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${intensity * 100}%`,
                        background: isBest
                          ? "linear-gradient(90deg, #ff5b1f, #f7c948)"
                          : isToday
                          ? "linear-gradient(90deg, #ff5b1f, #ff7a3f)"
                          : "rgba(255, 255, 255, 0.18)",
                      }}
                    />
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    <span className="font-display text-xl leading-none font-mono-num text-white">
                      {count}
                    </span>
                    {isBest && (
                      <span className="text-[9px] font-bold tracking-[0.15em] px-1.5 py-0.5 rounded bg-[color:var(--color-gold)]/15 text-[color:var(--color-gold)] border border-[color:var(--color-gold)]/30">
                        BEST
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      {/* --------------- series --------------- */}
      <Section title="Séries en cours" accent="emerald" className="mt-4">
        {series.length === 0 ? (
          <p className="text-sm text-[color:var(--color-text-mute)]">
            Aucune série active
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {series.map((s) => {
              const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
              const maxLeft = 7 - s.home_wins - s.away_wins;
              const estLeft = Math.round((minLeft + maxLeft) / 2);
              const atRisk =
                Math.max(s.home_wins, s.away_wins) === 3 &&
                Math.min(s.home_wins, s.away_wins) < 3;
              return (
                <div
                  key={s.id}
                  className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/[0.04]"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono-num font-bold text-sm text-[color:var(--color-text)] tracking-wide">
                      {s.home_team}
                    </span>
                    <span className="font-mono-num font-bold text-[color:var(--color-flame)]">
                      {s.home_wins}
                    </span>
                    <span className="text-[color:var(--color-text-mute)] text-xs">
                      —
                    </span>
                    <span className="font-mono-num font-bold text-[color:var(--color-flame)]">
                      {s.away_wins}
                    </span>
                    <span className="font-mono-num font-bold text-sm text-[color:var(--color-text)] tracking-wide">
                      {s.away_team}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {atRisk && (
                      <span className="text-[9px] font-bold tracking-[0.15em] px-1.5 py-0.5 rounded bg-[color:var(--color-crimson)]/15 text-[color:var(--color-crimson)] border border-[color:var(--color-crimson)]/30 animate-pulse-red">
                        ELIM
                      </span>
                    )}
                    <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--color-text-mute)] font-mono-num">
                      ~{estLeft}g
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({
  title,
  accent,
  children,
  className = "",
}: {
  title: string;
  accent: "gold" | "violet" | "emerald";
  children: React.ReactNode;
  className?: string;
}) {
  const accentColor = {
    gold: "text-[color:var(--color-gold)]",
    violet: "text-[color:var(--color-violet)]",
    emerald: "text-[color:var(--color-emerald)]",
  }[accent];

  const accentLine = {
    gold: "bg-[color:var(--color-gold)]",
    violet: "bg-[color:var(--color-violet)]",
    emerald: "bg-[color:var(--color-emerald)]",
  }[accent];

  return (
    <section
      className={`relative overflow-hidden rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] p-4 ${className}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className={`h-[3px] w-6 rounded-full ${accentLine}`} />
        <h2
          className={`font-display text-sm tracking-[0.2em] uppercase ${accentColor}`}
        >
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function CapitalTile({
  value,
  label,
  stars,
  color,
  borderColor,
  bgColor,
}: {
  value: number;
  label: string;
  stars: string;
  color: string;
  borderColor: string;
  bgColor: string;
}) {
  return (
    <div
      className={`rounded-[var(--radius-card-sm)] border ${borderColor} ${bgColor} p-3 text-center`}
    >
      <div className={`text-xs ${color}`}>{stars}</div>
      <div
        className={`font-display text-4xl leading-none font-mono-num ${color} mt-1`}
      >
        {value}
      </div>
      <div
        className={`text-[9px] uppercase tracking-[0.2em] ${color} opacity-80 mt-1.5`}
      >
        {label}
      </div>
    </div>
  );
}
