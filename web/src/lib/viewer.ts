import "server-only";
import { cache } from "react";
import { createAuthClient } from "@/lib/supabase/server";
import { adminClient } from "@/lib/supabase/admin";
import { isOwnerEmail } from "./owner";

type MinimalAuthClient = {
  auth: { getUser(): Promise<{ data: { user: { email?: string | null } | null } }> };
};

async function resolveViewer(
  getClient: () => Promise<MinimalAuthClient> = createAuthClient,
): Promise<{ owner: boolean }> {
  try {
    const supabase = await getClient();
    const { data } = await supabase.auth.getUser();
    return { owner: isOwnerEmail(data.user?.email ?? null, process.env.OWNER_EMAIL) };
  } catch {
    return { owner: false };
  }
}

/** Session → mode public/connecté. Ne lève jamais : session expirée ou
 *  cookies absents (PWA iPhone) donnent `owner: false`, jamais une
 *  exception qui ferait planter une page. `getClient` est injectable pour
 *  les tests (vitest alias "server-only" en module vide). Enveloppé par
 *  `cache()` (React) : le layout et la page ne font qu'une seule
 *  vérification de session par requête serveur, appelée sans argument. */
export const getViewer = cache(resolveViewer);

/** Client service (contourne la RLS), seulement après vérification de la
 *  session propriétaire — jamais exposé au mode public (migration 028). */
export async function ownerDb(
  getClient?: () => Promise<MinimalAuthClient>,
): Promise<ReturnType<typeof adminClient> | null> {
  // Appel sans argument quand possible (cas normal, hors tests) pour
  // partager l'entrée de cache() avec l'appel fait par le layout.
  const viewer = getClient ? await getViewer(getClient) : await getViewer();
  return viewer.owner ? adminClient() : null;
}
