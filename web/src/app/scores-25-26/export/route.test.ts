import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchScoresMock } = vi.hoisted(() => ({ fetchScoresMock: vi.fn() }));
vi.mock("../data", () => ({ fetchScores: fetchScoresMock }));

import { GET } from "./route";

function req(qs = ""): Request {
  return new Request(`http://localhost/scores-25-26/export${qs}`);
}

beforeEach(() => {
  fetchScoresMock.mockReset();
});

describe("GET /scores-25-26/export", () => {
  it("renvoie un CSV avec le bon statut, content-type, BOM et Content-Disposition pour les paramètres par défaut", async () => {
    fetchScoresMock.mockResolvedValue({
      available: true,
      rows: [
        {
          playerId: 1,
          name: "Jayson Tatum",
          team: "BOS",
          games: 40,
          avgTtfl: 45.5,
          totalTtfl: 1820,
          topScore: 78,
          topDate: "2025-11-03",
          topOpponent: "NYK",
        },
      ],
    });

    const res = await GET(req());

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("text/csv; charset=utf-8");
    expect(res.headers.get("content-disposition")).toBe(
      'attachment; filename="scores-ttfl-2025-26-regular.csv"',
    );
    const bytes = new Uint8Array(await res.clone().arrayBuffer());
    // BOM UTF-8 : EF BB BF (Response.text() le décode et le retire via
    // TextDecoder — on vérifie les octets bruts).
    expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf]);
    const body = await res.text();
    expect(body).toContain("Jayson Tatum;BOS;40;45,5;78;03/11;NYK");
    expect(fetchScoresMock).toHaveBeenCalledWith("regular", 20, null);
  });

  it("propage type/équipe/minimum dans la requête et le nom de fichier", async () => {
    fetchScoresMock.mockResolvedValue({ available: true, rows: [] });

    const res = await GET(req("?type=playoffs&team=nyk&min=8"));

    expect(res.status).toBe(200);
    expect(res.headers.get("content-disposition")).toBe(
      'attachment; filename="scores-ttfl-2025-26-playoffs-nyk.csv"',
    );
    expect(fetchScoresMock).toHaveBeenCalledWith("playoffs", 8, "NYK");
  });

  it("trie selon sort/dir avant d'écrire le CSV", async () => {
    fetchScoresMock.mockResolvedValue({
      available: true,
      rows: [
        {
          playerId: 1,
          name: "B",
          team: "BOS",
          games: 40,
          avgTtfl: 30,
          totalTtfl: 1200,
          topScore: 60,
          topDate: "2025-11-01",
          topOpponent: "NYK",
        },
        {
          playerId: 2,
          name: "A",
          team: "NYK",
          games: 40,
          avgTtfl: 50,
          totalTtfl: 2000,
          topScore: 40,
          topDate: "2025-11-02",
          topOpponent: "BOS",
        },
      ],
    });

    const res = await GET(req("?sort=avg&dir=asc"));
    const body = await res.text();
    const lines = body.slice(1).split("\r\n").filter(Boolean);

    // en-tête (lines[0]) puis B (moyenne 30) avant A (moyenne 50) en tri croissant.
    expect(lines[1].startsWith("B;")).toBe(true);
    expect(lines[2].startsWith("A;")).toBe(true);
  });

  it("renvoie 400 pour un type invalide, sans appeler fetchScores", async () => {
    const res = await GET(req("?type=foo"));
    expect(res.status).toBe(400);
    expect(fetchScoresMock).not.toHaveBeenCalled();
  });

  it("renvoie 400 pour une équipe inconnue", async () => {
    const res = await GET(req("?team=ZZZ"));
    expect(res.status).toBe(400);
  });

  it("renvoie 400 pour un minimum hors bornes", async () => {
    const res = await GET(req("?min=999"));
    expect(res.status).toBe(400);
  });

  it("renvoie 503 quand la vue est indisponible (migration pas encore appliquée)", async () => {
    fetchScoresMock.mockResolvedValue({ available: false, rows: [] });
    const res = await GET(req());
    expect(res.status).toBe(503);
  });
});
