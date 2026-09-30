import { beforeEach, describe, expect, it, vi } from "vitest";

// Aucune base en test : getPronoCore est mocké (le reste de core.ts n'est
// pas utilisé par la route image).
const getPronoCore = vi.fn();
vi.mock("@/app/pronos-26-27/core", () => ({ getPronoCore: (id: unknown) => getPronoCore(id) }));

import { GET } from "./route";

const ID = "11111111-1111-4111-8111-111111111111";

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

const req = new Request(`http://localhost/pronos-26-27/${ID}/image`);

describe("GET /pronos-26-27/[id]/image", () => {
  beforeEach(() => getPronoCore.mockReset());

  it("prono connu : 200, image/png, vrai PNG (rendu complet, polices locales)", async () => {
    getPronoCore.mockResolvedValue({
      id: ID,
      name: "Jean Dupont — Élan <b>ÉÀÇ</b>",
      wins: { BOS: 60, NYK: 55, OKC: 64, DEN: 52 },
      updatedAt: "2026-10-01T10:00:00Z",
      createdAt: "2026-10-01T09:00:00Z",
    });
    const res = await GET(req, ctx(ID));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    expect(res.headers.get("cache-control")).toMatch(/no-store/);
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47]);
    expect(bytes.length).toBeGreaterThan(10_000);
    expect(getPronoCore).toHaveBeenCalledWith(ID);
  }, 30_000);

  it("prono inconnu ou id invalide : 404", async () => {
    getPronoCore.mockResolvedValue(null);
    const res = await GET(req, ctx("pas-un-uuid"));
    expect(res.status).toBe(404);
  });
});
