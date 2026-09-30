import { createHash } from "crypto";
import { describe, expect, it } from "vitest";
import { createPronoCore, getClosure, getPronoCore, listPronosCore, savePronoCore, type ProNoDeps } from "./core";

// Client service factice, injectable via le paramètre `deps` de chaque
// fonction *Core (jamais exposé sur les server actions publiques — voir
// actions.ts et core.ts). Chaque appel `db.from(...)` est enregistré
// (opération, arguments d'insert/update, filtres `.eq`) pour pouvoir
// vérifier CE QUI est écrit, pas seulement que l'appel a réussi (revue
// round 1, important 3).
type Result = { data?: unknown; error?: { code?: string; message?: string } | null; count?: number | null };
type RecordedCall = { op: "select" | "insert" | "update" | null; payload?: unknown; filters: Record<string, unknown> };

function builder(result: Result, onTerminal: (call: RecordedCall) => void) {
  const call: RecordedCall = { op: null, filters: {} };
  const self = {
    select: () => {
      if (!call.op) call.op = "select";
      return self;
    },
    insert: (payload: unknown) => {
      call.op = "insert";
      call.payload = payload;
      return self;
    },
    update: (payload: unknown) => {
      call.op = "update";
      call.payload = payload;
      return self;
    },
    eq: (col: string, val: unknown) => {
      call.filters[col] = val;
      return self;
    },
    not: () => self,
    order: () => self,
    limit: () => self,
    maybeSingle: async () => {
      onTerminal(call);
      return result;
    },
    single: async () => {
      onTerminal(call);
      return result;
    },
    then: (resolve: (r: Result) => void) => {
      onTerminal(call);
      resolve(result);
    },
  };
  return self;
}

/** File de résultats consommée dans l'ordre des appels `db.from(...)` faits
 *  par la fonction *Core testée ; `calls` accumule ce qui a été envoyé à
 *  chaque appel (select/insert/update + filtres). */
function fakeAdmin(results: Result[]) {
  let i = 0;
  const calls: RecordedCall[] = [];
  const admin = {
    from: () => {
      const result = results[Math.min(i, results.length - 1)];
      i++;
      return builder(result, (call) => calls.push(call));
    },
  } as unknown as NonNullable<ProNoDeps["admin"]>;
  return { admin, calls };
}

function hash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

const FUTURE = new Date("2026-10-01T00:00:00Z"); // avant l'échéance
const DEADLINE = new Date("2026-10-20T23:00:00Z");
const AFTER_DEADLINE_NOW = new Date("2026-10-21T00:00:00Z");
const VALID_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_VALID_ID = "22222222-2222-4222-8222-222222222222";

describe("createPronoCore", () => {
  it("crée un prono, renvoie un jeton en clair, jamais journalisé/relu ; name_key/token_hash corrects", async () => {
    const { admin, calls } = fakeAdmin([
      { count: 2, error: null }, // comptage < 30
      { data: { id: VALID_ID }, error: null }, // insertion
    ]);
    const result = await createPronoCore("  JEAN   Dupont ", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.id).toBe(VALID_ID);
      expect(result.data.token).toMatch(/^[A-Za-z0-9_-]{20,}$/); // base64url, 32 octets

      const insertCall = calls.find((c) => c.op === "insert");
      const payload = insertCall?.payload as { name: string; name_key: string; token_hash: string; wins: unknown };
      expect(payload.name).toBe("JEAN   Dupont".replace(/\s+/g, " ").trim()); // nettoyé (espaces), casse conservée
      expect(payload.name_key).toBe("jean dupont");
      expect(payload.token_hash).toBe(hash(result.data.token)); // le hash stocké correspond au jeton renvoyé
      expect(payload.wins).toEqual({});
      expect("token" in (payload as object)).toBe(false); // jamais le jeton en clair dans la ligne insérée
    }
  });

  it("refuse un nom qui n'est pas une chaîne (valeur désérialisée arbitraire)", async () => {
    const result = await createPronoCore(42, { now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Nom invalide." });
  });

  it("refuse un nom trop court ou trop long", async () => {
    expect((await createPronoCore("A", { now: FUTURE, deadline: DEADLINE })).ok).toBe(false);
    expect((await createPronoCore("x".repeat(31), { now: FUTURE, deadline: DEADLINE })).ok).toBe(false);
  });

  it("Review Focus 2 — refuse la création après la clôture", async () => {
    const result = await createPronoCore("Jean Dupont", { now: AFTER_DEADLINE_NOW, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." });
  });

  it("Review Focus 4 — refuse un nom déjà pris à la casse/espaces près (violation unique en base)", async () => {
    const { admin } = fakeAdmin([
      { count: 1, error: null },
      {
        data: null,
        error: { code: "23505", message: 'duplicate key value violates unique constraint "season_pronos_season_name_key_key"' },
      },
    ]);
    const result = await createPronoCore("  JEAN   dupont ", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Ce nom est déjà pris." });
  });

  it("refuse au-delà de la limite de 30 pronos", async () => {
    const { admin } = fakeAdmin([{ count: 30, error: null }]);
    const result = await createPronoCore("Nouveau", { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Limite de 30 pronostics atteinte pour cette saison." });
  });
});

describe("savePronoCore", () => {
  it("Review Focus 1 — refuse sans jeton", async () => {
    const result = await savePronoCore(VALID_ID, "", { BOS: 50 }, { now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("Jeton");
  });

  it("Review Focus 1 — refuse un jeton invalide (appel direct de la fonction sans passer par l'UI)", async () => {
    const realToken = "le-vrai-jeton";
    const { admin } = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await savePronoCore(VALID_ID, "un-autre-jeton", { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("Jeton invalide");
  });

  it("important 2 — refuse un jeton non-chaîne ou trop long sans planter (pas de createHash().update() sur un type invalide)", async () => {
    const raw = savePronoCore as unknown as (...args: unknown[]) => Promise<{ ok: boolean; error?: string }>;
    await expect(raw(VALID_ID, 12345, { BOS: 50 }, { now: FUTURE, deadline: DEADLINE })).resolves.toEqual({
      ok: false,
      error: "Jeton invalide : ce prono appartient à quelqu'un d'autre.",
    });
    await expect(raw(VALID_ID, "x".repeat(101), { BOS: 50 }, { now: FUTURE, deadline: DEADLINE })).resolves.toEqual({
      ok: false,
      error: "Jeton invalide : ce prono appartient à quelqu'un d'autre.",
    });
  });

  it("important 2 — id non-UUID traité comme introuvable, sans requête ni exception", async () => {
    const result = await savePronoCore("../../etc/passwd", "un-jeton", { BOS: 50 }, { now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Prono introuvable." });
  });

  it("accepte le bon jeton, enregistre sur le bon id (filtre .eq)", async () => {
    const realToken = "le-vrai-jeton";
    const { admin, calls } = fakeAdmin([
      { data: { token_hash: hash(realToken) }, error: null },
      { data: null, error: null }, // update
    ]);
    const result = await savePronoCore(VALID_ID, realToken, { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: true, data: undefined });

    const updateCall = calls.find((c) => c.op === "update");
    expect(updateCall?.filters.id).toBe(VALID_ID);
    expect(updateCall?.payload).toEqual({ wins: { BOS: 50 } });
  });

  it("Review Focus 2 — refuse la modification après la clôture, même avec le bon jeton", async () => {
    const realToken = "le-vrai-jeton";
    const { admin } = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await savePronoCore(VALID_ID, realToken, { BOS: 50 }, { admin, now: AFTER_DEADLINE_NOW, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." });
  });

  it("refuse une carte de victoires invalide (équipe inconnue)", async () => {
    const realToken = "le-vrai-jeton";
    const { admin } = fakeAdmin([{ data: { token_hash: hash(realToken) }, error: null }]);
    const result = await savePronoCore(VALID_ID, realToken, { XXX: 10 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result.ok).toBe(false);
  });

  it("prono introuvable (id au format UUID valide mais absent en base)", async () => {
    const { admin } = fakeAdmin([{ data: null, error: null }]);
    const result = await savePronoCore(OTHER_VALID_ID, "un-jeton", { BOS: 50 }, { admin, now: FUTURE, deadline: DEADLINE });
    expect(result).toEqual({ ok: false, error: "Prono introuvable." });
  });

  it("Review Focus 3 — deux écritures séquentielles sur le même prono (deux onglets) : la dernière gagne, sans erreur", async () => {
    const realToken = "le-vrai-jeton";
    // Une seule ligne factice partagée : chaque UPDATE réécrit son `wins`,
    // donc l'état final observable est celui de la DERNIÈRE écriture — un
    // bug qui inverserait l'ordre ou perdrait une écriture ferait échouer
    // ce test (contrairement à la version précédente, à état non partagé,
    // qui ne pouvait pas échouer).
    const row: { token_hash: string; wins: unknown } = { token_hash: hash(realToken), wins: {} };
    const updateCalls: unknown[] = [];
    const admin = {
      from: () => {
        const self = {
          select: () => self,
          update: (payload: { wins: unknown }) => {
            updateCalls.push(payload.wins);
            row.wins = payload.wins;
            return self;
          },
          eq: () => self,
          maybeSingle: async () => ({ data: { token_hash: row.token_hash }, error: null }),
          then: (resolve: (r: { data: null; error: null }) => void) => resolve({ data: null, error: null }),
        };
        return self;
      },
    } as unknown as NonNullable<ProNoDeps["admin"]>;

    const first = await savePronoCore(VALID_ID, realToken, { BOS: 40 }, { admin, now: FUTURE, deadline: DEADLINE });
    const second = await savePronoCore(VALID_ID, realToken, { BOS: 55 }, { admin, now: FUTURE, deadline: DEADLINE });

    expect(first).toEqual({ ok: true, data: undefined });
    expect(second).toEqual({ ok: true, data: undefined });
    expect(updateCalls).toEqual([{ BOS: 40 }, { BOS: 55 }]);
    expect(row.wins).toEqual({ BOS: 55 }); // dernière écriture gagne
  });
});

describe("listPronosCore / getPronoCore", () => {
  it("listPronosCore ne renvoie jamais token_hash (non sélectionné en base)", async () => {
    const { admin } = fakeAdmin([
      {
        data: [{ id: VALID_ID, name: "Jean Dupont", wins: { BOS: 50 }, updated_at: "2026-10-05T00:00:00Z" }],
        error: null,
      },
    ]);
    const rows = await listPronosCore({ admin });
    expect(rows).toEqual([{ id: VALID_ID, name: "Jean Dupont", wins: { BOS: 50 }, updatedAt: "2026-10-05T00:00:00Z" }]);
    expect(JSON.stringify(rows)).not.toContain("token_hash");
  });

  it("getPronoCore renvoie null si l'id est absent en base", async () => {
    const { admin } = fakeAdmin([{ data: null, error: null }]);
    expect(await getPronoCore(VALID_ID, { admin })).toBeNull();
  });

  it("getPronoCore renvoie null pour un id malformé, sans requête", async () => {
    expect(await getPronoCore("' OR 1=1 --")).toBeNull();
    expect(await getPronoCore(123)).toBeNull();
    expect(await getPronoCore(null)).toBeNull();
  });

  it("getPronoCore renvoie le détail sans jeton", async () => {
    const { admin } = fakeAdmin([
      {
        data: {
          id: VALID_ID,
          name: "Jean Dupont",
          wins: { BOS: 50 },
          updated_at: "2026-10-05T00:00:00Z",
          created_at: "2026-10-01T00:00:00Z",
        },
        error: null,
      },
    ]);
    const row = await getPronoCore(VALID_ID, { admin });
    expect(row).toEqual({
      id: VALID_ID,
      name: "Jean Dupont",
      wins: { BOS: 50 },
      updatedAt: "2026-10-05T00:00:00Z",
      createdAt: "2026-10-01T00:00:00Z",
    });
  });
});

describe("getClosure", () => {
  it("ouvert avant l'échéance, échéance renvoyée en ISO", async () => {
    await expect(getClosure({ now: FUTURE, deadline: DEADLINE })).resolves.toEqual({
      closed: false,
      deadline: "2026-10-20T23:00:00.000Z",
    });
  });

  it("clos à l'échéance et après", async () => {
    expect((await getClosure({ now: DEADLINE, deadline: DEADLINE })).closed).toBe(true);
    expect((await getClosure({ now: AFTER_DEADLINE_NOW, deadline: DEADLINE })).closed).toBe(true);
  });

  it("client public en échec : repli sur l'échéance fixe, jamais d'exception", async () => {
    const broken = {
      from: () => {
        throw new Error("boom");
      },
    } as unknown as ProNoDeps["publicDb"];
    await expect(getClosure({ now: FUTURE, publicDb: broken })).resolves.toEqual({
      closed: false,
      deadline: "2026-10-20T23:00:00.000Z",
    });
  });
});
