import { timingSafeEqual } from "crypto";
import { NextRequest } from "next/server";
import { adminClient } from "@/lib/supabase/admin";
import { notifyAll } from "@/lib/notify";
import { deckDate } from "@/lib/date";
import { deckAlerts, dueReminders } from "@/lib/reminders";
import { addDays } from "@/lib/date";
import { DECK_CHECK_DAYS, loadDeckEntries } from "@/lib/deck-entries";

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

  let db: ReturnType<typeof adminClient>;
  try {
    db = adminClient();
  } catch (e) {
    console.error("adminClient() indisponible :", e instanceof Error ? e.message : e);
    return Response.json({ error: "Erreur serveur" }, { status: 500 });
  }
  const date = deckDate();

  const { data: night, error: nightErr } = await db
    .from("nights")
    .select("date, closing_at")
    .eq("date", date)
    .eq("is_phantom", false)
    .gt("n_eligible_games", 0)
    .maybeSingle();

  if (nightErr) {
    console.error("Échec de la requête nights :", nightErr.message ?? nightErr);
    return Response.json({ error: "nights" }, { status: 500 });
  }

  const now = new Date();
  let sentCount = 0;

  /** Réserve la clé (une seule alerte par changement), envoie, libère la
   *  réservation si rien n'a été délivré pour retenter au prochain run. */
  async function deliver(n: string, kind: string, key: string, title: string, body: string, closingAt: string) {
    const { error } = await db.from("reminders_sent").insert({ night: n, kind, key });
    if (error) {
      if ((error as { code?: string }).code === "23505") return; // déjà envoyé par un run concurrent
      console.error("Échec de la réservation du rappel :", error.message ?? error);
      return;
    }
    // M4 (revue finale) : TTL = temps restant avant la fermeture de la soirée.
    const ttlSeconds = Math.max(1, Math.round((new Date(closingAt).getTime() - now.getTime()) / 1000));
    let delivered = false;
    try {
      const result = await notifyAll({ title, body, url: "/", ttlSeconds });
      delivered = result.push > 0 || result.telegram;
    } catch (e) {
      console.error("Échec de notifyAll :", e instanceof Error ? e.message : e);
    }
    if (!delivered) {
      await db.from("reminders_sent").delete().eq("night", n).eq("kind", kind).eq("key", key);
      return;
    }
    sentCount += 1;
  }

  if (night) {
    const { data: pickRow, error: pickErr } = await db
      .from("picks")
      .select("player_id, players(name, injury_status)")
      .eq("date", date)
      .maybeSingle();

    if (pickErr) {
      console.error("Échec de la requête picks :", pickErr.message ?? pickErr);
      return Response.json({ error: "picks" }, { status: 500 });
    }

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
    for (const r of dueReminders({ now, night, pick, sent })) {
      await deliver(date, r.kind, r.key, r.title, r.body, night.closing_at);
    }
  }

  // Vérification du deck sur 7 jours (24/11/2026) : blessure d'un pick ou
  // autre joueur proposé par le moteur. Un échec ici ne doit pas faire
  // échouer les rappels du soir (la route est appelée sans surveillance).
  try {
    const entries = await loadDeckEntries(db, date);
    const { data: deckSent } = await db.from("reminders_sent").select("night, kind, key")
      .gte("night", date).lte("night", addDays(date, DECK_CHECK_DAYS - 1));
    const sent = new Set((deckSent ?? []).map((r: { night: string; kind: string; key: string }) => `${r.night}|${r.kind}|${r.key}`));
    const closing = new Map(entries.map((e) => [e.night, e.closingAt]));
    for (const a of deckAlerts({ now, entries, sent })) {
      await deliver(a.night, a.kind, a.key, a.title, a.body, closing.get(a.night)!);
    }
  } catch (e) {
    console.error("Échec de la vérification du deck :", e instanceof Error ? e.message : e);
  }

  return Response.json({ sent: sentCount });
}

export async function POST(req: NextRequest): Promise<Response> {
  return handle(req);
}

export async function GET(req: NextRequest): Promise<Response> {
  return handle(req);
}
