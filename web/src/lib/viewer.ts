import "server-only";
import { createAuthClient } from "@/lib/supabase/server";
import { adminClient } from "@/lib/supabase/admin";
import { isOwnerEmail } from "./owner";

type MinimalAuthClient = {
  auth: { getUser(): Promise<{ data: { user: { email?: string | null } | null } }> };
};

/** Session → mode public/connecté. Ne lève jamais : session expirée ou
 *  cookies absents (PWA iPhone) donnent `owner: false`, jamais une
 *  exception qui ferait planter une page. `getClient` est injectable pour
 *  les tests (vitest alias "server-only" en module vide). */
export async function getViewer(
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

/** Client service (contourne la RLS), seulement après vérification de la
 *  session propriétaire — jamais exposé au mode public (migration 028). */
export async function ownerDb(
  getClient?: () => Promise<MinimalAuthClient>,
): Promise<ReturnType<typeof adminClient> | null> {
  const viewer = await getViewer(getClient);
  return viewer.owner ? adminClient() : null;
}
