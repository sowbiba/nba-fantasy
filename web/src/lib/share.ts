// Partage de l'image d'un prono (bouton « Partager ») : Web Share API avec
// fichier quand le navigateur sait partager un png, sinon ouverture de
// l'image dans un nouvel onglet. Logique isolée ici, sans DOM global
// (navigateur, fetch et ouverture injectés), testée dans share.test.ts.

export type ShareNavigator = {
  canShare?: (data: ShareData) => boolean;
  share?: (data: ShareData) => Promise<void>;
};

/** Vrai seulement si le navigateur expose share + canShare et accepte un
 *  fichier png (Chrome/Safari mobiles ; faux sur la plupart des
 *  navigateurs de bureau). */
export function supportsFileShare(nav: ShareNavigator | undefined, probe: File): boolean {
  if (!nav || typeof nav.share !== "function" || typeof nav.canShare !== "function") return false;
  try {
    return nav.canShare({ files: [probe] });
  } catch {
    return false;
  }
}

export type ShareOutcome = "shared" | "opened" | "cancelled";

/** Doit être appelée directement dans le gestionnaire de clic : quand le
 *  partage de fichier n'est pas possible, l'image est ouverte AVANT tout
 *  `await` (sinon le bloqueur de pop-up refuse l'ouverture, le geste
 *  utilisateur étant perdu). */
export async function sharePronoImage(opts: {
  imageUrl: string;
  title: string;
  filename: string;
  nav: ShareNavigator | undefined;
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>;
  openUrl: (url: string) => void;
}): Promise<ShareOutcome> {
  const { imageUrl, title, filename, nav, fetchImpl, openUrl } = opts;
  const probe = new File([], filename, { type: "image/png" });
  if (!supportsFileShare(nav, probe)) {
    openUrl(imageUrl);
    return "opened";
  }

  let file: File;
  try {
    const res = await fetchImpl(imageUrl, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    file = new File([blob], filename, { type: "image/png" });
  } catch {
    openUrl(imageUrl);
    return "opened";
  }

  if (!supportsFileShare(nav, file)) {
    openUrl(imageUrl);
    return "opened";
  }

  try {
    await nav!.share!({ files: [file], title });
    return "shared";
  } catch (e) {
    if ((e as { name?: unknown } | null)?.name === "AbortError") return "cancelled";
    openUrl(imageUrl);
    return "opened";
  }
}
