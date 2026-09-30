import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock chaînable du client Supabase public (brief tâche 4 : "Mock the
// Supabase client in tests"). Chaque méthode se réenregistre elle-même sur
// l'objet retourné pour supporter n'importe quel enchaînement
// (from().select().eq().eq().gte()...), et l'objet est "thenable" pour
// résoudre `{ data, error, count }` quand la route/l'appelant `await`
// directement la query (comme le fait `@supabase/supabase-js`).
const { queryState, supabaseMock } = vi.hoisted(() => {
  const state: { data: unknown; error: unknown; count: number | null } = {
    data: [],
    error: null,
    count: null,
  };
  const calls: { method: string; args: unknown[] }[] = [];

  function makeChain(): Record<string, unknown> {
    const chain: Record<string, unknown> = {
      select: (...args: unknown[]) => {
        calls.push({ method: "select", args });
        return chain;
      },
      eq: (...args: unknown[]) => {
        calls.push({ method: "eq", args });
        return chain;
      },
      gte: (...args: unknown[]) => {
        calls.push({ method: "gte", args });
        return chain;
      },
      then: (resolve: (v: { data: unknown; error: unknown; count: number | null }) => unknown) =>
        Promise.resolve({ data: state.data, error: state.error, count: state.count }).then(resolve),
    };
    return chain;
  }

  const mock = {
    from: (...args: unknown[]) => {
      calls.push({ method: "from", args });
      return makeChain();
    },
    __calls: calls,
  };

  return { queryState: state, supabaseMock: mock };
});

vi.mock("@/lib/supabase/public", () => ({ supabase: supabaseMock }));

import { fetchScores } from "./data";

function calledWith(method: string, ...args: unknown[]): boolean {
  const calls = (supabaseMock as unknown as { __calls: { method: string; args: unknown[] }[] }).__calls;
  return calls.some((c) => c.method === method && JSON.stringify(c.args) === JSON.stringify(args));
}

beforeEach(() => {
  queryState.data = [];
  queryState.error = null;
  queryState.count = null;
  (supabaseMock as unknown as { __calls: unknown[] }).__calls.length = 0;
});

describe("fetchScores", () => {
  it("mappe les lignes de la vue vers ScoreRow", async () => {
    queryState.data = [
      {
        player_id: 42,
        name: "Jayson Tatum",
        team: "BOS",
        games: 40,
        avg_ttfl: "45.5",
        total_ttfl: "1820",
        top_score: 78,
        top_date: "2025-11-03",
        top_opponent: "NYK",
      },
    ];
    queryState.count = 1;

    const result = await fetchScores("regular", 20, null);

    expect(result.available).toBe(true);
    expect(result.rows).toEqual([
      {
        playerId: 42,
        name: "Jayson Tatum",
        team: "BOS",
        games: 40,
        avgTtfl: 45.5,
        totalTtfl: 1820,
        topScore: 78,
        topDate: "2025-11-03",
        topOpponent: "NYK",
      },
    ]);
  });

  it("filtre sur season/game_type/games, sans filtre équipe si aucune équipe demandée", async () => {
    await fetchScores("regular", 20, null);
    expect(calledWith("eq", "season", "2025-26")).toBe(true);
    expect(calledWith("eq", "game_type", "regular")).toBe(true);
    expect(calledWith("gte", "games", 20)).toBe(true);
    expect(calledWith("eq", "team", "NYK")).toBe(false);
  });

  it("ajoute le filtre équipe seulement quand une équipe est demandée", async () => {
    await fetchScores("playoffs", 5, "NYK");
    expect(calledWith("eq", "game_type", "playoffs")).toBe(true);
    expect(calledWith("eq", "team", "NYK")).toBe(true);
  });

  it("retourne available:false sans lever quand Supabase renvoie une erreur (ex. vue absente)", async () => {
    queryState.data = null;
    queryState.error = { message: "relation \"player_ttfl_season\" does not exist" };

    const result = await fetchScores("regular", 20, null);

    expect(result).toEqual({ rows: [], available: false });
  });

  it("journalise sans planter quand count dépasse le nombre de lignes renvoyées (troncature)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    queryState.data = [
      {
        player_id: 1,
        name: "A",
        team: "BOS",
        games: 20,
        avg_ttfl: 10,
        total_ttfl: 200,
        top_score: 20,
        top_date: "2025-11-01",
        top_opponent: "NYK",
      },
    ];
    queryState.count = 5; // count > data.length simule une troncature côté serveur.

    const result = await fetchScores("regular", 20, null);

    expect(result.available).toBe(true);
    expect(result.rows).toHaveLength(1);
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
