export function isOwnerEmail(email: string | null | undefined, owner: string | undefined): boolean {
  if (!email || !owner) return false;
  return email.trim().toLowerCase() === owner.trim().toLowerCase();
}

/** À appeler en premier dans chaque action serveur : les Server Functions
 *  sont joignables par POST direct, la session est la seule protection. */
export async function requireOwner(): Promise<string> {
  const { createAuthClient } = await import("@/lib/supabase/server");
  const supabase = await createAuthClient();
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email ?? null;
  if (!isOwnerEmail(email, process.env.OWNER_EMAIL)) {
    throw new Error("non_autorise");
  }
  return email!;
}
