import { describe, expect, it, vi } from "vitest";
import { fetchShareFile, shareCachedFile, shareFilename, supportsFileShare, type ShareNavigator } from "./share";

const IMAGE_URL = "/pronos-26-27/11111111-1111-4111-8111-111111111111/image";
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
const pngFile = () => new File([PNG], "prono-jean.png", { type: "image/png" });

function fileNav(share: ShareNavigator["share"] = vi.fn(async () => {})): ShareNavigator {
  return { canShare: (d) => Array.isArray(d.files) && d.files.length > 0, share };
}

describe("supportsFileShare", () => {
  const probe = new File([], "x.png", { type: "image/png" });
  it("faux sans navigateur, sans share ou sans canShare", () => {
    expect(supportsFileShare(undefined, probe)).toBe(false);
    expect(supportsFileShare({}, probe)).toBe(false);
    expect(supportsFileShare({ share: async () => {} }, probe)).toBe(false);
    expect(supportsFileShare({ canShare: () => true }, probe)).toBe(false);
  });
  it("faux si canShare refuse les fichiers ou lève une exception", () => {
    expect(supportsFileShare({ share: async () => {}, canShare: () => false }, probe)).toBe(false);
    const throwing = {
      share: async () => {},
      canShare: () => {
        throw new TypeError("nope");
      },
    };
    expect(supportsFileShare(throwing, probe)).toBe(false);
  });
  it("vrai si canShare accepte un fichier png", () => {
    expect(supportsFileShare(fileNav(), probe)).toBe(true);
  });
});

describe("shareCachedFile (appelé en première instruction du clic, sans await avant share)", () => {
  it("fichier prêt et partageable : navigator.share appelé de façon SYNCHRONE avec le File", async () => {
    const share = vi.fn(async () => {});
    const file = pngFile();
    const attempt = shareCachedFile(fileNav(share), file, "Prono de Jean");
    // Pas encore d'await : l'appel a déjà eu lieu (activation utilisateur préservée).
    expect(share).toHaveBeenCalledTimes(1);
    expect(share).toHaveBeenCalledWith({ files: [file], title: "Prono de Jean" });
    expect(attempt.kind).toBe("share");
    if (attempt.kind === "share") await expect(attempt.done).resolves.toBe("shared");
  });

  it("pas de fichier prêt : lien « Ouvrir l'image », share jamais appelé", () => {
    const share = vi.fn(async () => {});
    expect(shareCachedFile(fileNav(share), null, "t")).toEqual({ kind: "link" });
    expect(share).not.toHaveBeenCalled();
  });

  it("partage de fichier non supporté : lien", () => {
    expect(shareCachedFile({}, pngFile(), "t")).toEqual({ kind: "link" });
    expect(shareCachedFile(undefined, pngFile(), "t")).toEqual({ kind: "link" });
  });

  it("annulation (AbortError) → cancelled ; autre refus (NotAllowedError) → failed", async () => {
    const abort = vi.fn(async () => {
      throw new DOMException("annulé", "AbortError");
    });
    const a = shareCachedFile(fileNav(abort), pngFile(), "t");
    if (a.kind !== "share") throw new Error("attendu share");
    await expect(a.done).resolves.toBe("cancelled");

    const denied = vi.fn(async () => {
      throw new DOMException("refusé", "NotAllowedError");
    });
    const d = shareCachedFile(fileNav(denied), pngFile(), "t");
    if (d.kind !== "share") throw new Error("attendu share");
    await expect(d.done).resolves.toBe("failed");
  });

  it("share qui lève de façon synchrone : lien, jamais d'exception", () => {
    const nav: ShareNavigator = {
      canShare: () => true,
      share: () => {
        throw new TypeError("boom");
      },
    };
    expect(shareCachedFile(nav, pngFile(), "t")).toEqual({ kind: "link" });
  });
});

describe("fetchShareFile (pré-chargement de l'image)", () => {
  it("récupère l'image sans cache et renvoie un File png nommé", async () => {
    const fetchImpl = vi.fn(async () => new Response(PNG, { status: 200, headers: { "content-type": "image/png" } }));
    const file = await fetchShareFile({ imageUrl: IMAGE_URL, filename: "prono-jean.png", fetchImpl });
    expect(fetchImpl).toHaveBeenCalledWith(IMAGE_URL, { cache: "no-store" });
    expect(file?.name).toBe("prono-jean.png");
    expect(file?.type).toBe("image/png");
    expect(new Uint8Array(await file!.arrayBuffer())).toEqual(PNG);
  });

  it("HTTP en erreur ou réseau indisponible : null, jamais d'exception", async () => {
    const bad = vi.fn(async () => new Response("x", { status: 500 }));
    await expect(fetchShareFile({ imageUrl: IMAGE_URL, filename: "p.png", fetchImpl: bad })).resolves.toBeNull();
    const offline = vi.fn(async () => {
      throw new TypeError("réseau");
    });
    await expect(fetchShareFile({ imageUrl: IMAGE_URL, filename: "p.png", fetchImpl: offline })).resolves.toBeNull();
  });
});

describe("shareFilename", () => {
  it("nom de fichier ascii, sans accents ni caractères spéciaux", () => {
    expect(shareFilename("Jean Dupont")).toBe("prono-jean-dupont.png");
    expect(shareFilename("Élodie  O'Neil ✨")).toBe("prono-elodie-o-neil.png");
    expect(shareFilename("✨✨")).toBe("prono.png");
  });
});
