"use server";

import { createAuthClient } from "@/lib/supabase/server";

/** Envoie un code à 6 chiffres à OWNER_EMAIL (modèle d'e-mail Supabase avec
 *  {{ .Token }}). Aucun champ e-mail côté client : le code part toujours et
 *  uniquement à l'adresse configurée côté serveur, jamais révélée ici. */
export async function sendOwnerCode(): Promise<{ ok: boolean; error?: string }> {
  const owner = process.env.OWNER_EMAIL;
  if (!owner) {
    console.error("OWNER_EMAIL non défini");
    return { ok: false, error: "Connexion indisponible pour le moment." };
  }
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.signInWithOtp({ email: owner, options: { shouldCreateUser: false } });
  return error ? { ok: false, error: "Envoi impossible pour le moment, réessaie dans quelques minutes." } : { ok: true };
}

export async function verifyOwnerCode(code: string): Promise<{ ok: boolean; error?: string }> {
  const owner = process.env.OWNER_EMAIL;
  if (!owner) {
    console.error("OWNER_EMAIL non défini");
    return { ok: false, error: "Connexion indisponible pour le moment." };
  }
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.verifyOtp({ email: owner, token: code.replace(/\D/g, ""), type: "email" });
  return error ? { ok: false, error: "Code invalide ou expiré." } : { ok: true };
}
