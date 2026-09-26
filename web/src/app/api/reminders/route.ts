import { timingSafeEqual } from "crypto";
import { NextRequest } from "next/server";
import { adminClient } from "@/lib/supabase/admin";
import { notifyAll } from "@/lib/notify";
import { deckDate } from "@/lib/date";
import { dueReminders } from "@/lib/reminders";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type PlayerJoin = { name: string; injury_status: string | null };

type PickRow = { player_id: number; players: PlayerJoin | PlayerJoin[] | null };

function playerJoin(p: PickRow["players"]): PlayerJoin | null {
  if (!p) return null;
  return Array.isArray(p) ? p[0] ?? null : p;
}

/** Comparaison à temps constant : `timingSafeEqual` exige des buffers de
 *  même longueur, donc on compare d'abord les longueurs (fuite négligeable
 *  face au risque de planter sur des tailles différentes). */
function secretMatches(header: string | null, secret: string): boolean {
  if (!header?.startsWith("Bearer ")) return false;
  const provided = Buffer.from(header.slice("Bearer ".length));
  const expected = Buffer.from(secret);
  if (provided.length !== expected.length) return false;
  return timingSafeEqual(provided, expected);
}

async function handle(req: NextRequest): Promise<Response> {
  const secret = process.env.REMINDERS_SECRET;
  if (!secret) {
    console.error("REMINDERS_SECRET manquante");
    return Response.json({ error: "REMINDERS_SECRET manquante" }, { status: 500 });
  }
  if (!secretMatches(req.headers.get("authorization"), secret)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  const db = adminClient();
  const date = deckDate();

  const { data: night } = await db
    .from("nights")
    .select("date, closing_at")
    .eq("date", date)
    .eq("is_phantom", false)
    .gt("n_eligible_games", 0)
    .maybeSingle();

  if (!night) return Response.json({ sent: 0 });

  const { data: pickRow } = await db
    .from("picks")
    .select("player_id, players(name, injury_status)")
    .eq("date", date)
    .maybeSingle();

  const pick = pickRow
    ? (() => {
        const row = pickRow as unknown as PickRow;
        const player = playerJoin(row.players);
        // Un pick existe même si la jointure players échoue (données
        // incohérentes) : ne pas déclencher un faux rappel « pas de pick ».
        return { playerId: row.player_id, name: player?.name ?? "?", injuryStatus: player?.injury_status ?? null };
      })()
    : null;

  const { data: sentRows } = await db.from("reminders_sent").select("kind, key").eq("night", date);
  const sent = new Set((sentRows ?? []).map((r) => `${r.kind}|${r.key}`));

  const reminders = dueReminders({ now: new Date(), night, pick, sent });

  let sentCount = 0;
  for (const r of reminders) {
    const { error } = await db.from("reminders_sent").insert({ night: date, kind: r.kind, key: r.key });
    if (error) {
      if ((error as { code?: string }).code === "23505") continue; // déjà envoyé par un run concurrent
      console.error("Échec de la réservation du rappel :", error.message ?? error);
      continue;
    }
    let delivered = false;
    try {
      const result = await notifyAll({ title: r.title, body: r.body, url: "/" });
      delivered = result.push > 0 || result.telegram;
    } catch (e) {
      console.error("Échec de notifyAll :", e instanceof Error ? e.message : e);
    }
    if (!delivered) {
      // Rien n'a été délivré (ou notifyAll a levé) : on libère la réservation
      // pour retenter au prochain run (dans les 15 min).
      await db.from("reminders_sent").delete().eq("night", date).eq("kind", r.kind).eq("key", r.key);
      continue;
    }
    sentCount += 1;
  }

  return Response.json({ sent: sentCount });
}

export async function POST(req: NextRequest): Promise<Response> {
  return handle(req);
}

export async function GET(req: NextRequest): Promise<Response> {
  return handle(req);
}
