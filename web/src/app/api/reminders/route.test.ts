import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

// Revue fix round 1 : adminClient() (web/src/lib/supabase/admin.ts) lève
// synchroniquement si SUPABASE_SERVICE_KEY est absente — la route ne doit
// pas planter (elle est appelée par pg_cron toutes les 15 min), elle doit
// renvoyer le même contrat JSON 500 que pour REMINDERS_SECRET manquante.
describe("POST /api/reminders — adminClient() indisponible", () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    process.env.REMINDERS_SECRET = "test-secret";
    delete process.env.SUPABASE_SERVICE_KEY;
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  it("renvoie 500 JSON sans planter", async () => {
    const req = new NextRequest("http://localhost/api/reminders", {
      method: "POST",
      headers: { authorization: "Bearer test-secret" },
    });
    const res = await POST(req);
    expect(res.status).toBe(500);
    await expect(res.json()).resolves.toEqual({ error: "Erreur serveur" });
  });
});
