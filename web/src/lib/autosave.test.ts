import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAutosave, type AutosaveState } from "./autosave";

type R = { ok: true } | { ok: false; error: string };

function deferred() {
  let resolve!: (r: R) => void;
  const promise = new Promise<R>((res) => (resolve = res));
  return { promise, resolve };
}

describe("createAutosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("regroupe les modifications rapprochées (anti-rebond) et n'envoie que la dernière", async () => {
    const save = vi.fn(async (): Promise<R> => ({ ok: true }));
    const states: AutosaveState[] = [];
    const a = createAutosave<number>({ save, onState: (s) => states.push(s), delay: 800 });
    a.schedule(1);
    await vi.advanceTimersByTimeAsync(500);
    a.schedule(2);
    await vi.advanceTimersByTimeAsync(799);
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith(2);
    expect(states.map((s) => s.status)).toEqual(["pending", "saving", "saved"]);
  });

  it("n'écrase jamais la dernière saisie : une modif pendant un envoi est renvoyée ensuite", async () => {
    const first = deferred();
    const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue({ ok: true });
    const states: AutosaveState[] = [];
    const a = createAutosave<number>({ save, onState: (s) => states.push(s), delay: 800 });
    a.schedule(1);
    await vi.advanceTimersByTimeAsync(800);
    expect(save).toHaveBeenCalledTimes(1);
    a.schedule(2);
    a.schedule(3);
    await vi.advanceTimersByTimeAsync(800);
    // Envoi 1 toujours en cours : pas d'envoi parallèle.
    expect(save).toHaveBeenCalledTimes(1);
    first.resolve({ ok: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith(3);
    expect(states.at(-1)).toEqual({ status: "saved" });
    expect(states.filter((s) => s.status === "saved")).toHaveLength(1);
  });

  it("erreur : état erreur avec le message, la modif suivante renvoie tout", async () => {
    const save = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, error: "Erreur serveur, réessaie plus tard." })
      .mockResolvedValue({ ok: true });
    const states: AutosaveState[] = [];
    const a = createAutosave<number>({ save, onState: (s) => states.push(s), delay: 800 });
    a.schedule(1);
    await vi.advanceTimersByTimeAsync(800);
    expect(states.at(-1)).toEqual({ status: "error", error: "Erreur serveur, réessaie plus tard." });
    a.schedule(2);
    await vi.advanceTimersByTimeAsync(800);
    expect(save).toHaveBeenLastCalledWith(2);
    expect(states.at(-1)).toEqual({ status: "saved" });
  });

  it("exception réseau : état erreur générique, jamais d'exception remontée", async () => {
    const save = vi.fn().mockRejectedValue(new Error("fetch failed"));
    const states: AutosaveState[] = [];
    const a = createAutosave<number>({ save, onState: (s) => states.push(s), delay: 800 });
    a.schedule(1);
    await vi.advanceTimersByTimeAsync(800);
    expect(states.at(-1)?.status).toBe("error");
    expect(states.at(-1)?.error).toMatch(/connexion/i);
  });

  it("flush envoie immédiatement la saisie en attente, sans rien envoyer s'il n'y en a pas", async () => {
    const save = vi.fn(async (): Promise<R> => ({ ok: true }));
    const a = createAutosave<number>({ save, onState: () => {}, delay: 800 });
    a.flush();
    expect(save).not.toHaveBeenCalled();
    a.schedule(7);
    a.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(save).toHaveBeenCalledWith(7);
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("cancel annule l'envoi programmé", async () => {
    const save = vi.fn(async (): Promise<R> => ({ ok: true }));
    const a = createAutosave<number>({ save, onState: () => {}, delay: 800 });
    a.schedule(1);
    a.cancel();
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).not.toHaveBeenCalled();
  });
});
