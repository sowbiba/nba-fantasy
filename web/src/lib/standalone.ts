// Pages autonomes (pronos 2026-27, scores 2025-26) : destinées aux
// partenaires TTFL, elles s'affichent sans l'habillage de l'application
// (en-tête « Mode connecté », barre de navigation, tirer-pour-rafraîchir)
// mais gardent polices, styles globaux et fond sombre. Aucun lien vers ces
// pages depuis l'application. Liste unique, utilisée par AppChrome.

export const STANDALONE_PREFIXES = ["/pronos-26-27", "/scores-25-26"] as const;

/** Vrai pour le préfixe exact ou un de ses sous-chemins (`/pronos-26-27/…`),
 *  jamais pour un chemin qui ne ferait que commencer pareil
 *  (`/pronos-26-27x`). */
export function isStandalonePath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return STANDALONE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}
