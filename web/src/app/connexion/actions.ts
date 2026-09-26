"use server";

import { isOwnerEmail } from "@/lib/auth";
import { createAuthClient } from "@/lib/supabase/server";

/** Envoie un code à 6 chiffres (modèle d'e-mail Supabase avec {{ .Token }}).
 *  Réponse identique pour un e-mail non autorisé : on ne révèle rien. */
export async function sendCode(email: string): Promise<{ ok: boolean; error?: string }> {
  const clean = email.trim().toLowerCase();
  if (!isOwnerEmail(clean, process.env.OWNER_EMAIL)) return { ok: true };
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.signInWithOtp({ email: clean, options: { shouldCreateUser: false } });
  return error ? { ok: false, error: "Envoi impossible pour le moment, réessaie dans quelques minutes." } : { ok: true };
}

export async function verifyCode(email: string, code: string): Promise<{ ok: boolean; error?: string }> {
  const clean = email.trim().toLowerCase();
  if (!isOwnerEmail(clean, process.env.OWNER_EMAIL)) return { ok: false, error: "Code invalide ou expiré." };
  const supabase = await createAuthClient();
  const { error } = await supabase.auth.verifyOtp({ email: clean, token: code.replace(/\D/g, ""), type: "email" });
  return error ? { ok: false, error: "Code invalide ou expiré." } : { ok: true };
}
