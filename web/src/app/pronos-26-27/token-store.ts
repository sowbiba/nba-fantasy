"use client";

import { useSyncExternalStore } from "react";

// Jeton d'édition d'un prono, gardé UNIQUEMENT dans le localStorage de
// l'appareil qui l'a créé (clé `ttfl-prono-<id>`) : jamais dans une URL,
// jamais journalisé. Lecture via useSyncExternalStore (null au rendu
// serveur puis valeur réelle à l'hydratation, sans décalage d'hydratation
// ni setState dans un effet).

export function pronoTokenKey(id: string): string {
  return `ttfl-prono-${id}`;
}

function readToken(id: string): string | null {
  try {
    return window.localStorage.getItem(pronoTokenKey(id));
  } catch {
    // Stockage indisponible (navigation privée stricte, cookies bloqués).
    return null;
  }
}

/** Mémorise le jeton ; faux si le navigateur refuse le stockage. */
export function storeToken(id: string, token: string): boolean {
  try {
    window.localStorage.setItem(pronoTokenKey(id), token);
    return true;
  } catch {
    return false;
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/** `undefined` = pas encore lu (serveur/hydratation), `null` = absent. */
export function useStoredToken(id: string): string | null | undefined {
  return useSyncExternalStore<string | null | undefined>(
    subscribe,
    () => readToken(id),
    () => undefined,
  );
}
