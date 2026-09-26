import { createClient } from "@supabase/supabase-js";

/** Client anon, lecture seule (les écritures passent par app/actions.ts). */
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);
