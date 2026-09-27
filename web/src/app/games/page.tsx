import Link from "next/link";
import { supabase } from "@/lib/supabase/public";
import { Game } from "@/types";
import { addDays, frDayMonth, todayNBA, weekStart } from "@/lib/date";
import GamesList from "./GamesList";
import GamesTabs from "@/components/GamesTabs";

export const revalidate = 300;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

async function getData(start: string) {
  const { data } = await supabase.from("games").select("*")
    .gte("date", start).lte("date", addDays(start, 6))
    // Miroir de ELIGIBLE_TYPES (engine/rules/game_types.py, R4).
    .in("game_type", ["regular", "cup_final", "playoffs"])
    .order("date", { ascending: false }).limit(300);
  return { games: (data || []) as Game[] };
}

export default async function GamesPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { semaine } = await searchParams;
  const current = weekStart(todayNBA());
  const start = typeof semaine === "string" && ISO_DATE.test(semaine) ? weekStart(semaine) : current;
  const { games } = await getData(start);
  const isCurrent = start === current;

  const navLink = "px-3 py-2 rounded-[var(--radius-card-sm)] border border-white/10 bg-white/[0.02] text-sm text-white";

  return (
    <div className="px-4 py-5 animate-fade-in">
      <GamesTabs active="matchs" />
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-flame)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-flame)]" />
          Box scores
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          MATCH<span className="flame-text">S</span>
        </h1>
        <p className="text-[11px] text-[color:var(--color-text-mute)] mt-2 uppercase tracking-[0.18em]">
          {games.filter((g) => g.status === "final").length} terminé
          {games.filter((g) => g.status === "final").length > 1 ? "s" : ""} ·{" "}
          {games.filter((g) => g.status !== "final").length} à venir
        </p>
      </div>

      <nav className="flex items-center justify-between gap-2 mb-4" aria-label="Semaines">
        <Link href={`/games?semaine=${addDays(start, -7)}`} className={navLink} aria-label="Semaine précédente">←</Link>
        <div className="text-center">
          <div className="text-sm text-white">
            Semaine du {frDayMonth(start)} au {frDayMonth(addDays(start, 6))}
          </div>
          {!isCurrent && (
            <Link href="/games" className="text-[11px] text-[color:var(--color-text-mute)] underline">
              Revenir à cette semaine
            </Link>
          )}
        </div>
        <Link href={`/games?semaine=${addDays(start, 7)}`} className={navLink} aria-label="Semaine suivante">→</Link>
      </nav>

      <GamesList games={games} />
    </div>
  );
}
