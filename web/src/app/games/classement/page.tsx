import { supabase } from "@/lib/supabase/public";
import { StandingsRow } from "@/types";
import GamesTabs from "@/components/GamesTabs";
import StandingsTable from "@/components/StandingsTable";

// Vue publique (migration 027), même convention que /injuries : pas
// d'entrée dynamique (pas de searchParams/cookies), revalidée toutes les
// 5 minutes plutôt que lue à chaque requête.
export const revalidate = 300;

async function getData() {
  const { data } = await supabase.from("standings").select("*").order("conference").order("rank");
  return { rows: (data || []) as StandingsRow[] };
}

export default async function StandingsPage() {
  const { rows } = await getData();

  return (
    <div className="px-4 py-5 animate-fade-in">
      <GamesTabs active="classement" />
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-flame)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-flame)]" />
          NBA
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          CLASSE<span className="flame-text">MENT</span>
        </h1>
      </div>

      <StandingsTable rows={rows} />
    </div>
  );
}
