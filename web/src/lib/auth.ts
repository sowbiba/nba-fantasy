import "server-only";
import { createAuthClient } from "@/lib/supabase/server";
import { isOwnerEmail } from "./owner";

export { isOwnerEmail } from "./owner";

/** À appeler en premier dans chaque action serveur : les Server Functions
 *  sont joignables par POST direct, la session est la seule protection. */
export async function requireOwner(): Promise<string> {
  const supabase = await createAuthClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email ?? null;
  if (!isOwnerEmail(email, process.env.OWNER_EMAIL)) {
    throw new Error("non_autorise");
  }
  return email!;
}
