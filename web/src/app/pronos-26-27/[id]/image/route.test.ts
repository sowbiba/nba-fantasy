import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Aucune base en test : getPronoCore est mocké (le reste de core.ts n'est
// pas utilisé par la route image).
const getPronoCore = vi.fn();
vi.mock("@/app/pronos-26-27/core", () => ({ getPronoCore: (id: unknown) => getPronoCore(id) }));

import { GET } from "./route";
import { TEAMS } from "@/lib/pronos";

const ID = "11111111-1111-4111-8111-111111111111";

// Prono complet : 30 équipes, 1230 victoires (condition de l'image).
const COMPLETE: Record<string, number> = Object.fromEntries(TEAMS.map((t) => [t.code, 41]));
COMPLETE.BOS = 60;
COMPLETE.WAS = 22;

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

const req = new Request(`http://localhost/pronos-26-27/${ID}/image`);

function detail(name: string) {
  return {
    id: ID,
    name,
    wins: COMPLETE,
    updatedAt: "2026-10-01T10:00:00Z",
    createdAt: "2026-10-01T09:00:00Z",
  };
}

async function expectPng(res: Response) {
  expect(res.status).toBe(200);
  expect(res.headers.get("content-type")).toBe("image/png");
  const bytes = new Uint8Array(await res.arrayBuffer());
  expect(Array.from(bytes.slice(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47]);
  expect(bytes.length).toBeGreaterThan(10_000);
}

describe("GET /pronos-26-27/[id]/image", () => {
  // Aucun accès réseau autorisé pendant le rendu (polices/emoji de repli de
  // satori) : tout fetch vers le réseau lève une exception et est compté.
  // Seule exception : les URL `data:` — @vercel/og charge son wasm (resvg,
  // yoga) embarqué en base64 via fetch("data:…"), ce qui reste local.
  const realFetch = globalThis.fetch;
  const fetchSpy = vi.fn(async (input: unknown) => {
    throw new Error(`réseau interdit pendant le rendu de l'image : ${String(input).slice(0, 80)}`);
  });
  const guardedFetch = (input: unknown, init?: RequestInit) =>
    String(input).startsWith("data:") ? realFetch(input as string, init) : fetchSpy(input);
  beforeEach(() => {
    getPronoCore.mockReset();
    fetchSpy.mockClear();
    vi.stubGlobal("fetch", guardedFetch);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("prono connu : 200, image/png, vrai PNG (rendu complet, polices locales)", async () => {
    getPronoCore.mockResolvedValue({
      id: ID,
      name: "Jean Dupont — Élan <b>ÉÀÇ</b>",
      wins: COMPLETE,
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

  it("nom avec emoji, écritures non latines et caractères limites : 200 png sans aucun accès réseau", async () => {
    getPronoCore.mockResolvedValue(detail("🏀 Jokić ž Ő ș Łódź 李 — · ’ “ÀÿŒœ” € 🔥"));
    await expectPng(await GET(req, ctx(ID)));
  }, 30_000);

  it("nom entièrement hors police : repli « Prono », 200 png sans réseau", async () => {
    getPronoCore.mockResolvedValue(detail("🏀🔥✨"));
    await expectPng(await GET(req, ctx(ID)));
  }, 30_000);

  it("prono incomplet (équipes manquantes ou victoires non distribuées) : 409, pas d'image", async () => {
    const partial = { BOS: 60, NYK: 55 };
    const underCap = { ...COMPLETE, BOS: 59 }; // 30 équipes mais 1229 victoires
    for (const wins of [partial, underCap, {}]) {
      getPronoCore.mockResolvedValue({ ...detail("Jean"), wins });
      const res = await GET(req, ctx(ID));
      expect(res.status).toBe(409);
      expect(res.headers.get("content-type")).toMatch(/text\/plain/);
      expect(await res.text()).toMatch(/1 230 victoires/);
    }
  });

  it("getPronoCore renvoie null (prono absent ou id rejeté par core) : 404, id brut transmis tel quel", async () => {
    getPronoCore.mockResolvedValue(null);
    const res = await GET(req, ctx("pas-un-uuid"));
    expect(res.status).toBe(404);
    expect(getPronoCore).toHaveBeenCalledWith("pas-un-uuid");
  });
});
