import { supabase } from "@/lib/supabase";
import { Game } from "@/types";
import GamesList from "./GamesList";

export const revalidate = 300;

const PLAYOFFS_START = "2026-04-14";

async function getData() {
  const { data } = await supabase
    .from("games")
    .select("*")
    .gte("date", PLAYOFFS_START)
    .order("date", { ascending: false });

  return { games: (data || []) as Game[] };
}

export default async function GamesPage() {
  const { games } = await getData();

  return (
    <div className="px-4 py-5 animate-fade-in">
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

      <GamesList games={games} />
    </div>
  );
}
