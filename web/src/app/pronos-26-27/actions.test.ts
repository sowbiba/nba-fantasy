import { afterEach, describe, expect, it, vi } from "vitest";

// revalidatePath() exige un contexte de requête Next.js (store de
// génération statique) absent en test unitaire — sans rapport avec ce qui
// est testé ici, donc mocké en no-op.
vi.mock("next/cache", () => ({ revalidatePath: () => {} }));

import { createProno, saveProno } from "./actions";

// Revue round 1, critique 1 : `deps` (horloge/échéance/client injectés)
// vivait auparavant directement sur les server actions publiques — un
// appelant du RPC "use server" pouvait donc fournir son propre `deadline`
// dans le futur et contourner la clôture serveur (Review Focus 2). Les
// wrappers exportés ici (actions.ts) ne déclarent plus que les arguments
// métier nommés et ne les retransmettent jamais tels quels à core.ts — un
// argument supplémentaire, même façonné pour ressembler à `deps`, est donc
// simplement ignoré par la signature JS de la fonction appelée. On le
// prouve en appelant les wrappers avec un `deps`-like en argument
// surnuméraire (cast pour contourner la vérification TypeScript, comme le
// ferait un appel RPC direct qui n'est pas soumis au compilateur) et en
// vérifiant que la clôture réelle (horloge système + repli 2026-10-20
// 23:00Z, `@/lib/supabase/public` n'étant pas configuré en test) s'applique
// quand même.
const AFTER_FALLBACK_DEADLINE = new Date("2026-10-21T00:00:00Z");
const CLOSED_ERROR = { ok: false, error: "Les pronostics sont clos (le premier match de la saison a commencé)." };
const BOGUS_DEPS = { deadline: new Date("2099-01-01T00:00:00Z"), now: new Date("2000-01-01T00:00:00Z"), admin: {} };

describe("actions.ts — deps n'est pas un argument public des server actions", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("createProno : un 2ᵉ argument arbitraire (imitant deps) n'a aucun effet sur la clôture", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(AFTER_FALLBACK_DEADLINE);
    const raw = createProno as unknown as (...args: unknown[]) => Promise<unknown>;
    await expect(raw("Nom Valide", BOGUS_DEPS)).resolves.toEqual(CLOSED_ERROR);
  });

  it("saveProno : un 4ᵉ argument arbitraire (imitant deps) n'a aucun effet sur la clôture", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(AFTER_FALLBACK_DEADLINE);
    const raw = saveProno as unknown as (...args: unknown[]) => Promise<unknown>;
    await expect(raw("11111111-1111-4111-8111-111111111111", "un-jeton", { BOS: 50 }, BOGUS_DEPS)).resolves.toEqual(
      CLOSED_ERROR,
    );
  });
});
