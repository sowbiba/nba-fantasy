import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/** Client lié à la session de l'utilisateur (cookies). */
export async function createAuthClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            // Appelé depuis un Server Component (cookies en lecture seule) :
            // le rafraîchissement de session est fait par proxy.ts.
          }
        },
      },
    },
  );
}
