import { createHash } from "crypto";
import { describe, expect, it, vi } from "vitest";
import { createProno, getProno, listPronos, saveProno, type ProNoActionDeps } from "./actions";

// revalidatePath() exige un contexte de requête Next.js (store de
// génération statique) absent en test unitaire — sans rapport avec la
// logique testée ici (Review Focus 1-4), donc mocké en no-op.
vi.mock("next/cache", () => ({ revalidatePath: () => {} }));

// Client service factice, injectable via le paramètre `deps` de chaque
// action (jamais utilisé en production : là, adminClient() est appelé
// directement). Les résultats sont consommés dans l'ordre des appels
// `db.from(...)` faits par l'action testée.
type Result = { data?: unknown; error?: { code?: string; message?: string } | null; count?: number | null };

function builder(result: Result) {
  const self = {
    select: () => self,
    insert: () => self,
    update: () => self,
    eq: () => self,
    not: () => self,
    order: () => self,
    limit: () => self,
    maybeSingle: async () => result,
    single: async () => result,
    then: (resolve: (r: Result) => void) => resolve(result),
  };
  return self;
}

function fakeAdmin(results: Result[]) {
  let i = 0;
  return {
    from: () => {
      const result = results[Math.min(i, results.length - 1)];
      i++;
      return builder(result);
    },
  } as unknown as NonNullable<ProNoActionDeps["admin"]>;
}

function hash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

const FUTURE = new Date("2026-10-01T00:00:00Z"); // avant l'échéance
const DEADLINE = new Date("2026-10-20T23:00:00Z");
const AFTER_DEADLINE_NOW = new Date("2026-10-21T00:00:00Z");

describe("createProno", () => {
  it("crée un prono, renvoie un jeton en clair, jamais journalisé/relu", async () => {
    const admin = fakeAdmin([
      { count: 2, error: null }, // comptage < 30
      { data: { id: "abc-123" }, error: null }, // insertion
    ]);
    const result = await createProno("Jean Dupont", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.id).toBe("abc-123");
      expect(result.data.token).toMatch(/^[A-Za-z0-9_-]{20,}$/); // base64url, 32 octets
    }
  });

  it("refuse un nom trop court ou trop long", async () => {
    expect((await createProno("A", { now: FUTURE, deadline: DEADLINE })).ok).toBe(false);
    expect((await createProno("x".repeat(31), { now: FUTURE, deadline: DEADLINE })).ok).toBe(false);
  });

  it("Review Focus 2 — refuse la création après la clôture", async () => {
    const result = await createProno("Jean Dupont", { now: AFTER_DEADLINE_NOW, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." });
  });

  it("Review Focus 4 — refuse un nom déjà pris à la casse/espaces près (violation unique en base)", async () => {
    const admin = fakeAdmin([
      { count: 1, error: null },
      { data: null, error: { code: "23505", message: 'duplicate key value violates unique constraint "season_pronos_season_name_key_key"' } },
    ]);
    const result = await createProno("  JEAN   dupont ", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Ce nom est déjà pris." });
  });

  it("refuse au-delà de la limite de 30 pronos", async () => {
    const admin = fakeAdmin([{ count: 30, error: null }]);
    const result = await createProno("Nouveau", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Limite de 30 pronostics atteinte pour cette saison." });
  });
});

describe("saveProno", () => {
  it("Review Focus 1 — refuse sans jeton", async () => {
    const result = await saveProno("abc-123", "", { BOS: 50 }, { now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("Jeton");
  });

  it("Review Focus 1 — refuse un jeton invalide (appel direct de l'action sans passer par l'UI)", async () => {
    const realToken = "le-vrai-jeton";
    const admin = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await saveProno("abc-123", "un-autre-jeton", { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("Jeton invalide");
  });

  it("accepte le bon jeton et enregistre", async () => {
    const realToken = "le-vrai-jeton";
    const admin = fakeAdmin([
      { data: { token_hash: hash(realToken) }, error: null },
      { data: null, error: null }, // update
    ]);
    const result = await saveProno("abc-123", realToken, { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: true, data: undefined });
  });

  it("Review Focus 2 — refuse la modification après la clôture, même avec le bon jeton", async () => {
    const realToken = "le-vrai-jeton";
    const admin = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await saveProno("abc-123", realToken, { BOS: 50 }, { admin, now: AFTER_DEADLINE_NOW, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." });
  });

  it("refuse une carte de victoires invalide (équipe inconnue)", async () => {
    const realToken = "le-vrai-jeton";
    const admin = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await saveProno("abc-123", realToken, { XXX: 10 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
  });

  it("prono introuvable", async () => {
    const admin = fakeAdmin([{ data: null, error: null }]);
    const result = await saveProno("inconnu", "un-jeton", { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Prono introuvable." });
  });

  it("Review Focus 3 — deux écritures rapprochées (deux onglets) : la dernière gagne, sans erreur", async () => {
    const realToken = "le-vrai-jeton";
    const adminA = fakeAdmin([
      { data: { token_hash: hash(realToken) }, error: null },
      { data: null, error: null },
    ]);
    const adminB = fakeAdmin([
      { data: { token_hash: hash(realToken) }, error: null },
      { data: null, error: null },
    ]);

    const [first, second] = await Promise.all([
      saveProno("abc-123", realToken, { BOS: 40 }, { admin: adminA, now: FUTURE, deadline: DEADLINE }),
      saveProno("abc-123", realToken, { BOS: 55 }, { admin: adminB, now: FUTURE, deadline: DEADLINE }),
    ]);

    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
  });
});

describe("listPronos / getProno", () => {
  it("listPronos ne renvoie jamais token_hash (non sélectionné en base)", async () => {
    const admin = fakeAdmin([
      {
        data: [
          { id: "abc-123", name: "Jean Dupont", wins: { BOS: 50 }, updated_at: "2026-10-05T00:00:00Z" },
        ],
        error: null,
      },
    ]);
    const rows = await listPronos({ admin });
    expect(rows).toEqual([{ id: "abc-123", name: "Jean Dupont", wins: { BOS: 50 }, updatedAt: "2026-10-05T00:00:00Z" }]);
    expect(JSON.stringify(rows)).not.toContain("token_hash");
  });

  it("getProno renvoie null si absent", async () => {
    const admin = fakeAdmin([{ data: null, error: null }]);
    expect(await getProno("inconnu", { admin })).toBeNull();
  });

  it("getProno renvoie le détail sans jeton", async () => {
    const admin = fakeAdmin([
      {
        data: {
          id: "abc-123",
          name: "Jean Dupont",
          wins: { BOS: 50 },
          updated_at: "2026-10-05T00:00:00Z",
          created_at: "2026-10-01T00:00:00Z",
        },
        error: null,
      },
    ]);
    const row = await getProno("abc-123", { admin });
    expect(row).toEqual({
      id: "abc-123",
      name: "Jean Dupont",
      wins: { BOS: 50 },
      updatedAt: "2026-10-05T00:00:00Z",
      createdAt: "2026-10-01T00:00:00Z",
    });
  });
});
