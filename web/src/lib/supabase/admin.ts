import "server-only";
import { createClient } from "@supabase/supabase-js";

/** Client service (contourne la RLS) : UNIQUEMENT dans les actions serveur,
 *  après requireOwner(). */
export function adminClient() {
  if (!process.env.SUPABASE_SERVICE_KEY) {
    throw new Error("SUPABASE_SERVICE_KEY manquante");
  }
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
