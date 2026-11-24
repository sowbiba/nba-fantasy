import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// Chemin complet de la vérification du deck : la route charge le deck, le
// plan et les recos, puis envoie l'alerte et la réserve dans reminders_sent.
const state = vi.hoisted(() => ({ inserted: [] as unknown[], sent: [] as { title: string; body: string }[] }));

const TABLES: Record<string, unknown[]> = {
  nights: [{ date: "2026-11-27", closing_at: "2026-11-27T23:00:00Z" }],
  picks: [{ date: "2026-11-27", player_id: 1, players: { name: "Wembanyama", injury_status: "Day-To-Day" } }],
  plan: [{ generated_at: "2026-11-24T09:00:00Z", night: "2026-11-27", player_id: 2, projection: 29.6, p_play: 1,
           players: { name: "McDaniels" } }],
  recommendations: [],
  reminders_sent: [],
};

vi.mock("@/lib/supabase/admin", () => ({
  adminClient: () => ({
    from: (table: string) => {
      const result = { data: TABLES[table] ?? [], error: null };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const chain: any = {
        select: () => chain, eq: () => chain, gt: () => chain, gte: () => chain, lte: () => chain,
        order: () => chain, limit: () => chain, delete: () => chain,
        maybeSingle: async () => ({ data: null, error: null }),   // pas de soirée ce soir
        insert: async (row: unknown) => { state.inserted.push(row); return { error: null }; },
        then: (resolve: (v: typeof result) => unknown) => resolve(result),
      };
      return chain;
    },
  }),
}));

vi.mock("@/lib/notify", () => ({
  notifyAll: async (msg: { title: string; body: string }) => { state.sent.push(msg); return { push: 1, telegram: false }; },
}));

describe("POST /api/reminders — vérification du deck", () => {
  const ORIGINAL_ENV = { ...process.env };
  beforeEach(() => {
    process.env.REMINDERS_SECRET = "test-secret";
    process.env.SUPABASE_SERVICE_KEY = "irrelevant-with-mock";
    state.inserted = []; state.sent = [];
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-24T10:00:00Z"));   // 11:00 Paris
  });
  afterEach(() => { process.env = { ...ORIGINAL_ENV }; vi.useRealTimers(); });

  it("pick blessé dans 3 jours : alerte envoyée avec le remplaçant du plan", async () => {
    const { POST } = await import("./route");
    const res = await POST(new NextRequest("http://localhost/api/reminders", {
      method: "POST", headers: { authorization: "Bearer test-secret" },
    }));
    await expect(res.json()).resolves.toEqual({ sent: 1 });
    expect(state.sent[0].title).toBe("Deck 27/11 : Wembanyama (Day-To-Day)");
    expect(state.sent[0].body).toContain("McDaniels");
    expect(state.inserted).toEqual([{ night: "2026-11-27", kind: "deck_injury", key: "1:Day-To-Day" }]);
  });
});
