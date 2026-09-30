// Partage de l'image d'un prono (bouton « Partager »). Sans DOM global
// (navigateur et fetch injectés), testé dans share.test.ts.
//
// Contrainte iOS Safari (revue task 3, I1) : navigator.share doit être
// appelé pendant l'activation utilisateur du clic, donc SANS aucun await
// avant. L'image est donc pré-chargée (fetchShareFile) et le clic partage
// le fichier déjà en mémoire (shareCachedFile, synchrone). Quand ce n'est
// pas possible (pas de partage de fichier, image pas encore prête, refus),
// l'appelant affiche un vrai lien « Ouvrir l'image » plutôt qu'un
// window.open après await, que les bloqueurs de pop-up refuseraient.

export type ShareNavigator = {
  canShare?: (data: ShareData) => boolean;
  share?: (data: ShareData) => Promise<void>;
};

/** Vrai seulement si le navigateur expose share + canShare et accepte ce
 *  fichier (Chrome/Safari mobiles ; faux sur la plupart des navigateurs
 *  de bureau). */
export function supportsFileShare(nav: ShareNavigator | undefined, file: File): boolean {
  if (!nav || typeof nav.share !== "function" || typeof nav.canShare !== "function") return false;
  try {
    return nav.canShare({ files: [file] });
  } catch {
    return false;
  }
}

export type ShareAttempt =
  | { kind: "share"; done: Promise<"shared" | "cancelled" | "failed"> }
  | { kind: "link" };

/** À appeler en PREMIÈRE instruction du gestionnaire de clic : lance
 *  navigator.share de façon synchrone avec le fichier pré-chargé, ou
 *  demande l'affichage du lien si le partage de fichier est impossible. */
export function shareCachedFile(nav: ShareNavigator | undefined, file: File | null, title: string): ShareAttempt {
  if (!file || !supportsFileShare(nav, file)) return { kind: "link" };
  let pending: Promise<void>;
  try {
    pending = nav!.share!({ files: [file], title });
  } catch {
    return { kind: "link" };
  }
  return {
    kind: "share",
    done: Promise.resolve(pending).then(
      () => "shared" as const,
      (e: unknown) => ((e as { name?: unknown } | null)?.name === "AbortError" ? "cancelled" : "failed"),
    ),
  };
}

/** Pré-charge l'image (sans cache : elle change à chaque enregistrement).
 *  null en cas d'échec, jamais d'exception. */
export async function fetchShareFile(opts: {
  imageUrl: string;
  filename: string;
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>;
}): Promise<File | null> {
  try {
    const res = await opts.fetchImpl(opts.imageUrl, { cache: "no-store" });
    if (!res.ok) return null;
    const blob = await res.blob();
    return new File([blob], opts.filename, { type: "image/png" });
  } catch {
    return null;
  }
}

/** « prono-jean-dupont.png » : ascii seulement (les applis de partage
 *  gèrent mal les noms de fichiers accentués). */
export function shareFilename(name: string): string {
  const slug = name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug ? `prono-${slug}.png` : "prono.png";
}
