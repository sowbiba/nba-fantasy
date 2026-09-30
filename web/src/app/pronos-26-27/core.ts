import "server-only";

import { randomBytes, createHash, timingSafeEqual } from "crypto";
import { adminClient } from "@/lib/supabase/admin";
import { nameKey, sanitizeName, validateWins, isClosed as isClosedPure, type WinsMap } from "@/lib/pronos";

// Logique métier des pronos 2026-27, isolée dans un module `server-only` et
// SÉPARÉE des exports "use server" de actions.ts (revue round 1, critique
// 1) : tout export d'un fichier "use server" est un point d'entrée RPC —
// n'importe qui peut appeler l'action avec les arguments de son choix,
// jamais seulement ceux que le client officiel envoie. Un paramètre `deps`
// (horloge, échéance, client injectés) exposé directement sur une action
// exportée serait donc contournable (ex. `createProno("x", { deadline:
// futureDate })`) et casserait la clôture serveur (Review Focus 2). Ici,
// `deps` n'existe que sur des fonctions NON exportées en "use server" — les
// wrappers de actions.ts ne transmettent jamais que les arguments métier
// nommés, avec `deps` réel (jamais fourni par un appelant), donc rien de
// contrôlable par le client ne peut atteindre ce module.

const SEASON = "2026-27";
const FALLBACK_DEADLINE = "2026-10-20T23:00:00Z";
const MAX_PRONOS = 30;
const NAME_MIN = 2;
const NAME_MAX = 30;
const MAX_TOKEN_LENGTH = 100; // Un jeton réel fait ~43 caractères (32 octets en base64url) ; large marge, pas de limite serrée à maintenir.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type AdminClient = ReturnType<typeof adminClient>;
// Import différé (voir resolveDeadline) : ne charge/n'instancie le client
// public (variables d'environnement requises) qu'à l'usage réel, jamais au
// chargement du module — important pour les tests, qui fixent `deadline`
// directement et ne devraient jamais dépendre des env vars publiques.
type PublicClient = typeof import("@/lib/supabase/public").supabase;

export type ActionResult<T = undefined> = { ok: true; data: T } | { ok: false; error: string };

export type ProNoSummary = { id: string; name: string; wins: WinsMap; updatedAt: string };
export type ProNoDetail = ProNoSummary & { createdAt: string };

/** Dépendances injectables (tests uniquement, sur les fonctions `*Core` non
 *  exposées en "use server") : en production, chaque fonction résout
 *  elle-même adminClient()/le client public et l'horloge/l'échéance
 *  réelles. `deadline` permet aux tests de fixer directement l'échéance
 *  sans avoir à simuler la requête `games`. */
export type ProNoDeps = { admin?: AdminClient; publicDb?: PublicClient; now?: Date; deadline?: Date };
type Deps = ProNoDeps;

/** Échéance de clôture : tip_off du premier match de saison régulière
 *  2026-27 dans `games` (table publique, client anon suffit), repli fixe
 *  si aucun match n'est encore en base OU si le client public ne peut pas
 *  être instancié (ex. variables d'environnement publiques absentes au
 *  déploiement — revue round 1, mineur 8 : ne jamais laisser planter la
 *  clôture, se replier plutôt que 500). */
async function resolveDeadline(db?: PublicClient): Promise<Date> {
  try {
    const client = db ?? (await import("@/lib/supabase/public")).supabase;
    const { data } = await client
      .from("games")
      .select("tip_off")
      .eq("season", SEASON)
      .eq("game_type", "regular")
      .not("tip_off", "is", null)
      .order("tip_off", { ascending: true })
      .limit(1)
      .maybeSingle();
    return data?.tip_off ? new Date(data.tip_off) : new Date(FALLBACK_DEADLINE);
  } catch (e) {
    console.error("resolveDeadline (repli sur l'échéance fixe) :", e instanceof Error ? e.message : e);
    return new Date(FALLBACK_DEADLINE);
  }
}

async function getDeadline(deps: Deps): Promise<Date> {
  if (deps.deadline) return deps.deadline;
  return resolveDeadline(deps.publicDb);
}

/** Client service, ou erreur générique si SUPABASE_SERVICE_KEY manque en
 *  environnement : ne jamais laisser adminClient() planter une action avec
 *  une exception non gérée (miroir de getAdmin() dans app/actions.ts). */
function getAdmin(deps: Deps): { db: AdminClient } | { err: ActionResult<never> } {
  if (deps.admin) return { db: deps.admin };
  try {
    return { db: adminClient() };
  } catch (e) {
    console.error("adminClient() indisponible :", e instanceof Error ? e.message : e);
    return { err: { ok: false, error: "Erreur serveur, réessaie plus tard." } };
  }
}

/** Comparaison à temps constant du jeton fourni contre le hash stocké.
 *  On hache d'abord le jeton fourni (sha256, sortie fixe 32 octets) : la
 *  comparaison porte donc toujours sur deux buffers de même longueur que
 *  celle de `tokenHash`, sauf si `tokenHash` lui-même est malformé — cas
 *  exclu par la longueur vérifiée avant l'appel à timingSafeEqual. */
function tokenMatches(token: string, tokenHash: string): boolean {
  const candidate = createHash("sha256").update(token).digest();
  let expected: Buffer;
  try {
    expected = Buffer.from(tokenHash, "hex");
  } catch {
    return false;
  }
  if (candidate.length !== expected.length) return false;
  return timingSafeEqual(candidate, expected);
}

function summary(row: { id: string; name: string; wins: unknown; updated_at: string }): ProNoSummary {
  return { id: row.id, name: row.name, wins: (row.wins ?? {}) as WinsMap, updatedAt: row.updated_at };
}

/** Une server action reçoit des valeurs désérialisées arbitraires — jamais
 *  garanti d'être le type déclaré côté TypeScript (revue round 1,
 *  important 2). Gardes explicites avant tout usage, plutôt que de laisser
 *  `.trim()`/`createHash().update()`/une requête sur un id non-UUID planter
 *  en 500 ou bruiter les logs. */
function isValidId(id: unknown): id is string {
  return typeof id === "string" && UUID_RE.test(id);
}

function tokenGuardError(token: unknown): string | null {
  if (token === undefined || token === null || token === "") {
    return "Jeton manquant : ce prono appartient à quelqu'un d'autre.";
  }
  if (typeof token !== "string" || token.length > MAX_TOKEN_LENGTH) {
    return "Jeton invalide : ce prono appartient à quelqu'un d'autre.";
  }
  return null;
}

/** Crée un prono : valide le nom (2-30 caractères après nettoyage Unicode),
 *  refuse après clôture ou au-delà de 30 pronos pour la saison, refuse un
 *  nom déjà pris (casse/espaces ignorés — contrainte unique (season,
 *  name_key) en base, message clair sur violation 23505). Renvoie le jeton
 *  en clair UNE SEULE FOIS : ne jamais le journaliser ni le relire depuis
 *  la base (seul le hash y est stocké). */
export async function createPronoCore(
  name: unknown,
  deps: Deps = {},
): Promise<ActionResult<{ id: string; token: string }>> {
  if (typeof name !== "string") {
    return { ok: false, error: "Nom invalide." };
  }
  const trimmed = sanitizeName(name);
  if (trimmed.length < NAME_MIN || trimmed.length > NAME_MAX) {
    return { ok: false, error: `Le nom doit contenir entre ${NAME_MIN} et ${NAME_MAX} caractères.` };
  }

  const now = deps.now ?? new Date();
  const deadline = await getDeadline(deps);
  if (isClosedPure(now, deadline)) {
    return { ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." };
  }

  const admin = getAdmin(deps);
  if ("err" in admin) return admin.err;
  const { db } = admin;

  const { count, error: countError } = await db
    .from("season_pronos")
    .select("id", { count: "exact", head: true })
    .eq("season", SEASON);
  if (countError) {
    console.error("createProno (comptage) :", countError.message);
    return { ok: false, error: "Erreur serveur, réessaie plus tard." };
  }
  if ((count ?? 0) >= MAX_PRONOS) {
    return { ok: false, error: `Limite de ${MAX_PRONOS} pronostics atteinte pour cette saison.` };
  }

  const token = randomBytes(32).toString("base64url");
  const tokenHash = createHash("sha256").update(token).digest("hex");
  const key = nameKey(trimmed);

  const { data, error } = await db
    .from("season_pronos")
    .insert({ season: SEASON, name: trimmed, name_key: key, wins: {}, token_hash: tokenHash })
    .select("id")
    .single();

  if (error || !data) {
    if (error?.code === "23505") return { ok: false, error: "Ce nom est déjà pris." };
    console.error("createProno (insertion) :", error?.message);
    return { ok: false, error: "Erreur serveur, réessaie plus tard." };
  }

  return { ok: true, data: { id: data.id as string, token } };
}

/** Met à jour les victoires d'un prono. Exige le jeton en clair (comparé
 *  au hash stocké, temps constant) ; refusé sans jeton, avec un jeton
 *  invalide, ou après la clôture. Deux écritures rapprochées (deux
 *  onglets) : chacune est un simple UPDATE, la dernière gagne sans erreur
 *  (aucun contrôle de version — Review Focus 3). */
export async function savePronoCore(
  id: unknown,
  token: unknown,
  wins: unknown,
  deps: Deps = {},
): Promise<ActionResult> {
  const tokenError = tokenGuardError(token);
  if (tokenError) return { ok: false, error: tokenError };
  const safeToken = token as string;

  if (!isValidId(id)) {
    return { ok: false, error: "Prono introuvable." };
  }

  const now = deps.now ?? new Date();
  const deadline = await getDeadline(deps);
  if (isClosedPure(now, deadline)) {
    return { ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." };
  }

  const validated = validateWins(wins);
  if (!validated.ok) return { ok: false, error: validated.error };

  const admin = getAdmin(deps);
  if ("err" in admin) return admin.err;
  const { db } = admin;

  const { data: row, error: fetchError } = await db
    .from("season_pronos")
    .select("token_hash")
    .eq("id", id)
    .eq("season", SEASON)
    .maybeSingle();

  if (fetchError) {
    console.error("saveProno (lecture) :", fetchError.message);
    return { ok: false, error: "Erreur serveur, réessaie plus tard." };
  }
  if (!row) return { ok: false, error: "Prono introuvable." };

  if (!tokenMatches(safeToken, row.token_hash as string)) {
    return { ok: false, error: "Jeton invalide : ce prono appartient à quelqu'un d'autre." };
  }

  const { error } = await db.from("season_pronos").update({ wins: validated.wins }).eq("id", id);
  if (error) {
    console.error("saveProno (écriture) :", error.message);
    return { ok: false, error: "Erreur serveur, réessaie plus tard." };
  }

  return { ok: true, data: undefined };
}

/** Liste tous les pronos de la saison (lecture publique — tout le monde
 *  voit tous les pronos). Ne renvoie jamais `token_hash`. */
export async function listPronosCore(deps: Deps = {}): Promise<ProNoSummary[]> {
  const admin = getAdmin(deps);
  if ("err" in admin) return [];
  const { db } = admin;

  const { data, error } = await db
    .from("season_pronos")
    .select("id, name, wins, updated_at")
    .eq("season", SEASON)
    .order("updated_at", { ascending: false });

  if (error || !data) {
    if (error) console.error("listPronos :", error.message);
    return [];
  }
  return data.map(summary);
}

/** Détail d'un prono (lecture publique, sans jeton). Id malformé (pas un
 *  UUID) : traité comme absent, sans requête ni bruit de log. */
export async function getPronoCore(id: unknown, deps: Deps = {}): Promise<ProNoDetail | null> {
  if (!isValidId(id)) return null;

  const admin = getAdmin(deps);
  if ("err" in admin) return null;
  const { db } = admin;

  const { data, error } = await db
    .from("season_pronos")
    .select("id, name, wins, updated_at, created_at")
    .eq("id", id)
    .eq("season", SEASON)
    .maybeSingle();

  if (error || !data) {
    if (error) console.error("getProno :", error.message);
    return null;
  }
  return { ...summary(data), createdAt: data.created_at };
}
