import Link from "next/link";
import { supabase } from "@/lib/supabase/public";
import { createAuthClient } from "@/lib/supabase/server";
import { isOwnerEmail } from "@/lib/auth";
import { deckDate, seasonForDate } from "@/lib/date";
import PicksHistory, { HistoryRow } from "./PicksHistory";
import SignOutButton from "./SignOutButton";

export const revalidate = 0;

type Stats = { nights: number; scored_nights: number; total: number; average: number | null; picks: number; zeros: number; x2_used: number };

export default async function PicksPage() {
  const today = deckDate();
  const season = seasonForDate(today);
  const auth = await createAuthClient();
  const { data: userData } = await auth.auth.getUser();
  const signedIn = isOwnerEmail(userData.user?.email, process.env.OWNER_EMAIL);

  const [statsRes, picksRes, scRes] = await Promise.all([
    supabase.rpc("period_stats", { p_season: season, p_mode: "regular", p_until: today }),
    supabase.from("picks").select("id, date, player_id, actual_score, is_x2, players(name, team)").eq("season", season).order("date", { ascending: false }),
    supabase.from("second_chances").select("pick_id"),
  ]);
  const stats = ((statsRes.data || [])[0] ?? null) as Stats | null;
  const withSc = new Set(((scRes.data || []) as { pick_id: number }[]).map((s) => s.pick_id));
  type Row = { id: number; date: string; player_id: number; actual_score: number | null; is_x2: boolean; players: { name: string; team: string } | null };
  const rows: HistoryRow[] = ((picksRes.data || []) as unknown as Row[]).map((p) => ({
    id: p.id, date: p.date, player_id: p.player_id, player_name: p.players?.name ?? `#${p.player_id}`,
    team: p.players?.team ?? "", actual_score: p.actual_score, is_x2: p.is_x2, has_second_chance: withSc.has(p.id),
  }));

  return (
    <div className="px-4 py-5 animate-fade-in">
      <div className="flex items-start justify-between">
        <h1 className="font-display text-4xl leading-none tracking-wide text-white">
          MES <span className="flame-text">PICKS</span>
        </h1>
        {signedIn ? <SignOutButton /> : (
          <Link href="/connexion" className="text-xs underline text-[color:var(--color-text-soft)]">Connexion</Link>
        )}
      </div>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1 uppercase tracking-[0.18em]">Saison {season}</p>

      <div className="grid grid-cols-3 gap-2 mt-4">
        {[
          { label: "Moyenne", value: stats?.average ?? "—" },
          { label: "Soirées", value: stats?.nights ?? 0 },
          { label: "Zéros", value: stats?.zeros ?? 0 },
        ].map((t) => (
          <div key={t.label} className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-2 py-3 text-center">
            <div className="font-display text-2xl leading-none text-white font-mono-num">{t.value}</div>
            <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-1.5">{t.label}</div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[color:var(--color-text-mute)] mt-2">
        Moyenne sur toutes les soirées éligibles : une soirée sans pick compte 0. x2 utilisés : {stats?.x2_used ?? 0}.
      </p>

      <div className="mt-5">
        <PicksHistory rows={rows} today={today} />
      </div>
    </div>
  );
}
