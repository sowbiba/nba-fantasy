import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

// I2 (final review) : si la requête nights ou picks échoue, la route doit
// répondre 500 sans rien envoyer — auparavant l'erreur était ignorée, ce qui
// pouvait déclencher un faux rappel « pas de pick » alors qu'un pick existe.
const state = vi.hoisted(() => ({ nightError: false, pickError: false, sentInsertCalled: false }));

vi.mock("@/lib/supabase/admin", () => ({
  adminClient: () => ({
    from: (table: string) => {
      const chain: {
        select: () => typeof chain;
        eq: () => typeof chain;
        gt: () => typeof chain;
        order: () => typeof chain;
        maybeSingle: () => Promise<{ data: unknown; error: { message: string } | null }>;
        insert: (payload: unknown) => Promise<{ error: null }>;
        delete: () => typeof chain;
      } = {
        select: () => chain,
        eq: () => chain,
        gt: () => chain,
        order: () => chain,
        maybeSingle: async () => {
          if (table === "nights") {
            if (state.nightError) return { data: null, error: { message: "boom nights" } };
            return { data: { date: "2026-01-01", closing_at: "2026-01-02T00:00:00Z" }, error: null };
          }
          if (table === "picks") {
            if (state.pickError) return { data: null, error: { message: "boom picks" } };
            return { data: null, error: null };
          }
          return { data: null, error: null };
        },
        insert: async () => {
          state.sentInsertCalled = true;
          return { error: null };
        },
        delete: () => chain,
      };
      return chain;
    },
  }),
}));

describe("POST /api/reminders — erreurs de requête", () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    process.env.REMINDERS_SECRET = "test-secret";
    process.env.SUPABASE_SERVICE_KEY = "irrelevant-with-mock";
    state.nightError = false;
    state.pickError = false;
    state.sentInsertCalled = false;
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  function req() {
    return new NextRequest("http://localhost/api/reminders", {
      method: "POST",
      headers: { authorization: "Bearer test-secret" },
    });
  }

  it("requête nights en échec : 500 JSON, rien n'est envoyé", async () => {
    state.nightError = true;
    const res = await POST(req());
    expect(res.status).toBe(500);
    await expect(res.json()).resolves.toEqual({ error: "nights" });
    expect(state.sentInsertCalled).toBe(false);
  });

  it("requête picks en échec : 500 JSON, rien n'est envoyé (pas de faux « pas de pick »)", async () => {
    state.pickError = true;
    const res = await POST(req());
    expect(res.status).toBe(500);
    await expect(res.json()).resolves.toEqual({ error: "picks" });
    expect(state.sentInsertCalled).toBe(false);
  });
});
