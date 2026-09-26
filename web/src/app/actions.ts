"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { addDays, deckDate } from "@/lib/date";
import { pickErrorMessage } from "@/lib/errors";
import { adminClient } from "@/lib/supabase/admin";
import { createAuthClient } from "@/lib/supabase/server";

export type ActionResult = { ok: true } | { ok: false; error: string };

const RESERVATION_DAYS = 14; // R9
const SECOND_CHANCE_DAYS = 7; // R15

async function owner(): Promise<ActionResult | null> {
  try {
    await requireOwner();
    return null;
  } catch {
    return { ok: false, error: "Connecte-toi pour enregistrer (menu Picks → Connexion)." };
  }
}

function refresh(playerId?: number) {
  revalidatePath("/");
  revalidatePath("/deck");
  revalidatePath("/picks");
  if (playerId) revalidatePath(`/player/${playerId}`);
}

/** R2 : un pick par soirée ; s'il existe, on remplace le joueur (UPDATE,
 *  revalidé par le trigger picks_validate). R9 : 14 jours d'avance max. */
export async function savePick(input: { date: string; playerId: number; gameId: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const today = deckDate();
  if (input.date < today) return { ok: false, error: "Cette soirée est passée." };
  if (input.date > addDays(today, RESERVATION_DAYS)) {
    return { ok: false, error: "Réservation possible jusqu'à 14 jours à l'avance." };
  }
  const db = adminClient();
  const { data: existing, error: readError } = await db.from("picks").select("id").eq("date", input.date).maybeSingle();
  if (readError) return { ok: false, error: pickErrorMessage(readError) };
  const { error } = existing
    ? await db.from("picks").update({ player_id: input.playerId, game_id: input.gameId }).eq("id", existing.id)
    : await db.from("picks").insert({ player_id: input.playerId, game_id: input.gameId, date: input.date });
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh(input.playerId);
  return { ok: true };
}

/** R10 : activable jusqu'à la fermeture (soirée ≥ aujourd'hui) ; l'unicité
 *  mensuelle et la fenêtre novembre-avril sont garanties par la base. */
export async function setX2(input: { date: string; value: boolean }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  if (input.date < deckDate()) return { ok: false, error: "Le x2 ne se modifie plus après la fermeture." };
  const { error } = await adminClient().from("picks").update({ is_x2: input.value }).eq("date", input.date);
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh();
  return { ok: true };
}

/** R15 : débloque le pick à 0 visé, du jour d'achat à achat + 7 jours. */
export async function addSecondChance(input: { pickId: number; boughtOn: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const db = adminClient();
  const { data: pick, error: readError } = await db.from("picks")
    .select("id, player_id, actual_score").eq("id", input.pickId).maybeSingle();
  if (readError || !pick) return { ok: false, error: "Pick introuvable." };
  if (pick.actual_score !== 0) return { ok: false, error: "La Seconde chance ne s'applique qu'à un pick à 0." };
  const { error } = await db.from("second_chances").insert({
    pick_id: pick.id, player_id: pick.player_id,
    bought_on: input.boughtOn, expires_on: addDays(input.boughtOn, SECOND_CHANCE_DAYS),
  });
  if (error) return { ok: false, error: error.code === "23505" ? "Seconde chance déjà enregistrée pour ce pick." : pickErrorMessage(error) };
  refresh(pick.player_id);
  return { ok: true };
}

/** Favoris (sans effet sur le moteur). */
export async function setWatchlist(input: { playerId: number; priority: 1 | 2 | 3 | null }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const db = adminClient();
  const { error } = input.priority === null
    ? await db.from("player_watchlist").delete().eq("player_id", input.playerId)
    : await db.from("player_watchlist").upsert({ player_id: input.playerId, priority: input.priority });
  if (error) return { ok: false, error: "Échec de la mise à jour des favoris." };
  revalidatePath(`/player/${input.playerId}`);
  return { ok: true };
}

export async function signOut(): Promise<ActionResult> {
  const supabase = await createAuthClient();
  await supabase.auth.signOut();
  refresh();
  return { ok: true };
}
