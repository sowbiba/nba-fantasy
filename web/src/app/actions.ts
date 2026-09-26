"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { addDays, deckDate, seasonForDate } from "@/lib/date";
import { pickErrorMessage } from "@/lib/errors";
import { isClosed } from "@/lib/display";
import { adminClient } from "@/lib/supabase/admin";
import { createAuthClient } from "@/lib/supabase/server";

export type ActionResult = { ok: true } | { ok: false; error: string };

type AdminClient = ReturnType<typeof adminClient>;

const RESERVATION_DAYS = 14; // R9
const SECOND_CHANCE_DAYS = 7; // Miroir de la règle R15 / migration 018 (bought_on + 7 = expires_on).

async function owner(): Promise<ActionResult | null> {
  try {
    await requireOwner();
    return null;
  } catch {
    return { ok: false, error: "Connecte-toi pour enregistrer (menu Picks → Connexion)." };
  }
}

/** Client service, ou erreur générique si SUPABASE_SERVICE_KEY manque en
 *  environnement (M1) : ne jamais laisser adminClient() planter une action
 *  côté client avec une exception non gérée. */
function getAdmin(): { db: AdminClient } | { err: ActionResult } {
  try {
    return { db: adminClient() };
  } catch (e) {
    console.error("adminClient() indisponible :", e instanceof Error ? e.message : e);
    return { err: { ok: false, error: "Erreur serveur, réessaie plus tard." } };
  }
}

/** R8 : la soirée ferme à nights.closing_at (minuit Paris, ou le premier
 *  tip-off de la soirée s'il est plus tôt). Pas de ligne nights pour cette
 *  date : on ne bloque pas ici, les contrôles de date (deckDate/RESERVATION_DAYS)
 *  suffisent déjà. */
async function nightClosed(db: AdminClient, date: string): Promise<ActionResult | null> {
  const { data: night } = await db.from("nights").select("closing_at").eq("date", date).maybeSingle();
  if (night && isClosed(night.closing_at)) return { ok: false, error: "La soirée est fermée." };
  return null;
}

function refresh(playerId?: number) {
  revalidatePath("/");
  revalidatePath("/deck");
  revalidatePath("/picks");
  if (playerId) revalidatePath(`/player/${playerId}`);
}

/** R2 : un pick par soirée ; s'il existe, on remplace le joueur (UPDATE,
 *  revalidé par le trigger picks_validate). R9 : 14 jours d'avance max.
 *  R8 : refusé une fois la soirée fermée. */
export async function savePick(input: { date: string; playerId: number; gameId: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const today = deckDate();
  if (input.date < today) return { ok: false, error: "Cette soirée est passée." };
  if (input.date > addDays(today, RESERVATION_DAYS)) {
    return { ok: false, error: "Réservation possible jusqu'à 14 jours à l'avance." };
  }
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const closed = await nightClosed(db, input.date);
  if (closed) return closed;
  const { data: existing, error: readError } = await db.from("picks").select("id").eq("date", input.date).maybeSingle();
  if (readError) return { ok: false, error: pickErrorMessage(readError) };
  const { error } = existing
    ? await db.from("picks").update({ player_id: input.playerId, game_id: input.gameId }).eq("id", existing.id)
    : await db.from("picks").insert({ player_id: input.playerId, game_id: input.gameId, date: input.date });
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh(input.playerId);
  return { ok: true };
}

/** Annule une réservation ou un pick pas encore scoré, pour libérer la
 *  soirée. Ce n'est légitime que tant que le pick n'a pas encore été saisi
 *  sur trashtalk.co (workflow app-first) : TrashTalk n'autorise pas de
 *  vider une soirée réservée (R2) une fois saisie là-bas — voir la note
 *  sous R2 dans docs/regles-ttfl.md. R8 : refusé une fois la soirée fermée. */
export async function cancelPick(input: { date: string }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  if (input.date < deckDate()) return { ok: false, error: "Cette soirée est passée." };
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const closed = await nightClosed(db, input.date);
  if (closed) return closed;
  const { data, error } = await db.from("picks")
    .delete().eq("date", input.date).is("actual_score", null).select("id");
  if (error) return { ok: false, error: pickErrorMessage(error) };
  if (!data?.length) return { ok: false, error: "Aucun pick annulable ce soir-là." };
  refresh();
  return { ok: true };
}

/** R10 : activable jusqu'à la fermeture (R8) ; l'unicité mensuelle et la
 *  fenêtre novembre-avril sont garanties par la base. */
export async function setX2(input: { date: string; value: boolean }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  if (input.date < deckDate()) return { ok: false, error: "Le x2 ne se modifie plus après la fermeture." };
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const closed = await nightClosed(db, input.date);
  if (closed) return closed;
  const { data, error } = await db.from("picks")
    .update({ is_x2: input.value }).eq("date", input.date).select("id");
  if (error) return { ok: false, error: pickErrorMessage(error) };
  if (!data?.length) return { ok: false, error: "Aucun pick ce soir-là : choisis d'abord un joueur." };
  refresh();
  return { ok: true };
}

/** R15 : débloque le pick à 0 visé, du jour d'achat (calculé côté serveur,
 *  jamais fourni par le client) à achat + 7 jours. */
export async function addSecondChance(input: { pickId: number }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const { data: pick, error: readError } = await db.from("picks")
    .select("id, player_id, actual_score").eq("id", input.pickId).maybeSingle();
  if (readError || !pick) return { ok: false, error: "Pick introuvable." };
  if (pick.actual_score !== 0) return { ok: false, error: "La Seconde chance ne s'applique qu'à un pick à 0." };
  const boughtOn = deckDate();
  const { error } = await db.from("second_chances").insert({
    pick_id: pick.id, player_id: pick.player_id,
    bought_on: boughtOn, expires_on: addDays(boughtOn, SECOND_CHANCE_DAYS),
  });
  if (error) return { ok: false, error: error.code === "23505" ? "Seconde chance déjà enregistrée pour ce pick." : pickErrorMessage(error) };
  refresh(pick.player_id);
  return { ok: true };
}

/** Favoris (sans effet sur le moteur). */
export async function setWatchlist(input: { playerId: number; priority: 1 | 2 | 3 | null }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const { error } = input.priority === null
    ? await db.from("player_watchlist").delete().eq("player_id", input.playerId)
    : await db.from("player_watchlist").upsert({ player_id: input.playerId, priority: input.priority });
  if (error) return { ok: false, error: "Échec de la mise à jour des favoris." };
  revalidatePath(`/player/${input.playerId}`);
  return { ok: true };
}

/** Correction d'une soirée passée de la saison (synchro TrashTalk oubliée) :
 *  lève la fermeture en base (correct_pick), jamais le cooldown. */
export async function correctPick(input: { date: string; playerId: number | null }): Promise<ActionResult> {
  const denied = await owner();
  if (denied) return denied;
  const today = deckDate();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.date) || input.date >= today) {
    return { ok: false, error: "Seules les soirées passées se corrigent ici." };
  }
  if (seasonForDate(input.date) !== seasonForDate(today)) {
    return { ok: false, error: "Seules les soirées de la saison en cours se corrigent." };
  }
  const admin = getAdmin();
  if ("err" in admin) return admin.err;
  const { db } = admin;
  const { error } = await db.rpc("correct_pick", { p_date: input.date, p_player_id: input.playerId });
  if (error) return { ok: false, error: pickErrorMessage(error) };
  refresh(input.playerId ?? undefined);
  return { ok: true };
}

/** Effectif actuel (players.active) des équipes qui jouent un match éligible
 *  ce soir-là, pour choisir le joueur à corriger. Limite connue et acceptée :
 *  un joueur transféré depuis se corrige en base à la demande. */
export async function playersForNight(date: string): Promise<{ id: number; name: string; team: string }[]> {
  if (await owner()) return [];
  const admin = getAdmin();
  if ("err" in admin) return [];
  const { db } = admin;
  const { data: games } = await db.from("games").select("home_team, away_team")
    .eq("date", date).in("game_type", ["regular", "cup_final", "playoffs"]);
  const teams = [...new Set((games ?? []).flatMap((g) => [g.home_team, g.away_team]))];
  if (!teams.length) return [];
  const { data } = await db.from("players").select("id, name, team")
    .in("team", teams).eq("active", true).order("name");
  return data ?? [];
}

export async function signOut(): Promise<ActionResult> {
  const supabase = await createAuthClient();
  await supabase.auth.signOut();
  refresh();
  return { ok: true };
}
