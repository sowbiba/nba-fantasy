import { describe, expect, it, vi } from "vitest";
import { sharePronoImage, supportsFileShare, type ShareNavigator } from "./share";

const IMAGE_URL = "/pronos-26-27/11111111-1111-4111-8111-111111111111/image";
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);

function okFetch() {
  return vi.fn(async () => new Response(PNG, { status: 200, headers: { "content-type": "image/png" } }));
}

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
    expect(
      supportsFileShare({
        share: async () => {},
        canShare: () => {
          throw new TypeError("nope");
        },
      }, probe),
    ).toBe(false);
  });
  it("vrai si canShare accepte un fichier png", () => {
    expect(supportsFileShare(fileNav(), probe)).toBe(true);
  });
});

describe("sharePronoImage", () => {
  const base = { imageUrl: IMAGE_URL, title: "Prono de Jean", filename: "prono-jean.png" };

  it("sans partage de fichier : ouvre l'image tout de suite, sans fetch (geste utilisateur préservé)", async () => {
    const fetchImpl = okFetch();
    const openUrl = vi.fn();
    const promise = sharePronoImage({ ...base, nav: {}, fetchImpl, openUrl });
    // Appel synchrone, avant tout await : sinon les bloqueurs de pop-up refusent.
    expect(openUrl).toHaveBeenCalledWith(IMAGE_URL);
    await expect(promise).resolves.toBe("opened");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("partage de fichier possible : récupère l'image (sans cache) et partage un File png", async () => {
    const fetchImpl = okFetch();
    const share = vi.fn(async () => {});
    const openUrl = vi.fn();
    await expect(sharePronoImage({ ...base, nav: fileNav(share), fetchImpl, openUrl })).resolves.toBe("shared");
    expect(fetchImpl).toHaveBeenCalledWith(IMAGE_URL, { cache: "no-store" });
    expect(openUrl).not.toHaveBeenCalled();
    const data = (share.mock.calls[0] as unknown as [ShareData])[0];
    expect(data.title).toBe("Prono de Jean");
    expect(data.files).toHaveLength(1);
    const file = data.files![0];
    expect(file.name).toBe("prono-jean.png");
    expect(file.type).toBe("image/png");
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(PNG);
  });

  it("annulation par l'utilisateur (AbortError) : rien d'autre", async () => {
    const share = vi.fn(async () => {
      throw new DOMException("annulé", "AbortError");
    });
    const openUrl = vi.fn();
    await expect(sharePronoImage({ ...base, nav: fileNav(share), fetchImpl: okFetch(), openUrl })).resolves.toBe(
      "cancelled",
    );
    expect(openUrl).not.toHaveBeenCalled();
  });

  it("échec du partage (autre erreur) : repli sur l'ouverture de l'image", async () => {
    const share = vi.fn(async () => {
      throw new DOMException("refusé", "NotAllowedError");
    });
    const openUrl = vi.fn();
    await expect(sharePronoImage({ ...base, nav: fileNav(share), fetchImpl: okFetch(), openUrl })).resolves.toBe(
      "opened",
    );
    expect(openUrl).toHaveBeenCalledWith(IMAGE_URL);
  });

  it("image indisponible (HTTP en erreur ou réseau) : repli sur l'ouverture", async () => {
    const openUrl = vi.fn();
    const bad = vi.fn(async () => new Response("x", { status: 500 }));
    await expect(sharePronoImage({ ...base, nav: fileNav(), fetchImpl: bad, openUrl })).resolves.toBe("opened");
    const offline = vi.fn(async () => {
      throw new TypeError("réseau");
    });
    await expect(sharePronoImage({ ...base, nav: fileNav(), fetchImpl: offline, openUrl })).resolves.toBe("opened");
    expect(openUrl).toHaveBeenCalledTimes(2);
  });

  it("canShare refuse le vrai fichier : repli sur l'ouverture", async () => {
    let calls = 0;
    const nav: ShareNavigator = { share: vi.fn(async () => {}), canShare: () => ++calls === 1 };
    const openUrl = vi.fn();
    await expect(sharePronoImage({ ...base, nav, fetchImpl: okFetch(), openUrl })).resolves.toBe("opened");
    expect(nav.share).not.toHaveBeenCalled();
  });
});
