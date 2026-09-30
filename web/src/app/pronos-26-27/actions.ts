"use server";

import { revalidatePath } from "next/cache";
import { createPronoCore, savePronoCore, listPronosCore, getPronoCore } from "./core";

export type { ActionResult, ProNoSummary, ProNoDetail } from "./core";

// Server actions publiques (pas d'auteur/propriétaire à vérifier — cette
// page est pour les partenaires TTFL de l'utilisateur), mais chaque export
// d'un fichier "use server" est un point d'entrée RPC : n'importe qui peut
// appeler l'action avec les arguments de son choix. Ces wrappers ne
// transmettent donc JAMAIS que les arguments métier nommés ci-dessous à
// core.ts — jamais de `deps`, jamais `...arguments` — pour que rien de
// fourni par l'appelant ne puisse atteindre l'horloge, l'échéance ou le
// client service utilisés là-bas (revue round 1, critique 1). La logique et
// les gardes runtime vivent dans ./core.ts (`server-only`, testé
// directement dans core.test.ts).

export async function createProno(name: string) {
  const result = await createPronoCore(name);
  if (result.ok) revalidatePath("/pronos-26-27");
  return result;
}

export async function saveProno(id: string, token: string, wins: unknown) {
  const result = await savePronoCore(id, token, wins);
  if (result.ok) {
    revalidatePath(`/pronos-26-27/${id}`);
    revalidatePath("/pronos-26-27");
  }
  return result;
}

export async function listPronos() {
  return listPronosCore();
}

export async function getProno(id: string) {
  return getPronoCore(id);
}
