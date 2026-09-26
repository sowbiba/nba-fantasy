import { describe, expect, it } from "vitest";
import { homeState, recMeta } from "./display";

describe("recMeta", () => {
  it("formate les colonnes S1", () => {
    expect(recMeta({ p_play: 0.55, value: 31.24, locked_until: "2026-12-02", best_future: "vendredi 20/11 @ WAS · 50 pts projetés" }))
      .toEqual({ pPlay: "55 %", value: "31.2", lockedUntil: "02/12", bestFuture: "vendredi 20/11 @ WAS · 50 pts projetés" });
  });
  it("ne plante pas sur une ligne antérieure à la migration 020", () => {
    expect(recMeta({ p_play: null, value: null, locked_until: null, best_future: null }))
      .toEqual({ pPlay: null, value: null, lockedUntil: null, bestFuture: null });
  });
});

describe("homeState", () => {
  it("pas de soirée", () => expect(homeState({ hasNight: false, recCount: 0, hasPick: false })).toBe("no_games"));
  it("soirée sans recos : on attend la synchro, jamais les recos d'hier", () =>
    expect(homeState({ hasNight: true, recCount: 0, hasPick: false })).toBe("waiting_sync"));
  it("pick déjà posé", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: true })).toBe("picked"));
  it("à picker", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: false })).toBe("to_pick"));
});
