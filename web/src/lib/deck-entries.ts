import { addDays } from "@/lib/date";
import type { DeckEntry } from "@/lib/reminders";

/** Horizon de la vérification du deck (soirée du jour comprise). */
export const DECK_CHECK_DAYS = 7;
/** Le soir même, la reco n°1 ne remplace le pick qu'au-delà de cette marge
 *  (miroir de CHALLENGE_MARGIN, engine/strategy/regular.py). */
export const TONIGHT_MARGIN = 3;

type Named = { name: string; injury_status?: string | null };
type Join = Named | Named[] | null;
const one = (p: Join): Named | null => (Array.isArray(p) ? p[0] ?? null : p);

export type NightRow = { date: string; closing_at: string };
export type PickRow = { date: string; player_id: number; players: Join };
export type PlanRow = { night: string; player_id: number; projection: number; p_play: number; players: Join };
export type RecoRow = { player_id: number; rank: number; estimated_score: number | null; players: Join };

/** Assemble, pour chaque soirée, le pick du deck et la proposition du moteur :
 *  le soir même, la reco n°1 si elle dépasse le pick de plus de
 *  TONIGHT_MARGIN ; les soirs suivants, le dernier plan (qui applique déjà
 *  cette marge aux réservations). Pure. */
export function buildDeckEntries(input: {
  today: string; nights: NightRow[]; picks: PickRow[]; plan: PlanRow[]; tonightRecos: RecoRow[];
}): DeckEntry[] {
  const { today, nights, picks, plan, tonightRecos } = input;
  const pickBy = new Map(picks.map((p) => [p.date, p]));
  const planBy = new Map(plan.map((p) => [p.night, p]));
  return nights.map((n) => {
    const pr = pickBy.get(n.date);
    const pj = pr ? one(pr.players) : null;
    const pick = pr ? { playerId: pr.player_id, name: pj?.name ?? "?", injuryStatus: pj?.injury_status ?? null } : null;
    let proposal: DeckEntry["proposal"] = null;
    if (n.date === today) {
      const top = [...tonightRecos].sort((a, b) => a.rank - b.rank)[0];
      if (top) {
        const mine = tonightRecos.find((r) => r.player_id === pick?.playerId);
        const gap = (top.estimated_score ?? 0) - (mine?.estimated_score ?? 0);
        const better = !pick || (top.player_id !== pick.playerId && (!mine || gap > TONIGHT_MARGIN));
        proposal = better
          ? { playerId: top.player_id, name: one(top.players)?.name ?? "?", expected: top.estimated_score ?? 0 }
          : pick && { playerId: pick.playerId, name: pick.name, expected: mine?.estimated_score ?? 0 };
      }
    } else {
      const pl = planBy.get(n.date);
      if (pl) {
        proposal = { playerId: pl.player_id, name: one(pl.players)?.name ?? "?",
                     expected: Number(pl.projection) * Number(pl.p_play) };
      }
    }
    return { night: n.date, closingAt: n.closing_at, pick, proposal };
  });
}

type Res<T> = { data: T[] | null; error: { message?: string } | null };

/** Charge les soirées, picks, dernier plan et recos du soir sur l'horizon. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function loadDeckEntries(db: any, today: string): Promise<DeckEntry[]> {
  const last = addDays(today, DECK_CHECK_DAYS - 1);
  const nights: Res<NightRow> = await db.from("nights").select("date, closing_at")
    .gte("date", today).lte("date", last).eq("is_phantom", false).gt("n_eligible_games", 0);
  const picks: Res<PickRow> = await db.from("picks").select("date, player_id, players(name, injury_status)")
    .gte("date", today).lte("date", last);
  const latest: Res<{ generated_at: string }> = await db.from("plan").select("generated_at")
    .order("generated_at", { ascending: false }).limit(1);
  const generatedAt = latest.data?.[0]?.generated_at;
  const plan: Res<PlanRow> = generatedAt
    ? await db.from("plan").select("night, player_id, projection, p_play, players(name)")
        .eq("generated_at", generatedAt).gte("night", today).lte("night", last)
    : { data: [], error: null };
  const recos: Res<RecoRow> = await db.from("recommendations")
    .select("player_id, rank, estimated_score, players(name)").eq("date", today);
  for (const [what, r] of [["nights", nights], ["picks", picks], ["plan", latest], ["plan", plan], ["recommendations", recos]] as const) {
    if (r.error) throw new Error(`${what} : ${r.error.message ?? r.error}`);
  }
  return buildDeckEntries({ today, nights: nights.data ?? [], picks: picks.data ?? [], plan: plan.data ?? [],
                            tonightRecos: recos.data ?? [] });
}
