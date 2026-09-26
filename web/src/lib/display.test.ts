import { describe, expect, it } from "vitest";
import { homeState, pickPoints, recMeta } from "./display";

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

describe("pickPoints", () => {
  it("score positif x2 : doublé", () => expect(pickPoints(31, true)).toBe(62));
  it("score négatif x2 : doublé aussi (double faute)", () => expect(pickPoints(-4, true)).toBe(-8));
  it("zéro : reste zéro, x2 ou pas", () => {
    expect(pickPoints(0, true)).toBe(0);
    expect(pickPoints(0, false)).toBe(0);
  });
  it("pas encore scoré : null", () => expect(pickPoints(null, false)).toBeNull());
});

describe("homeState", () => {
  it("pas de soirée", () => expect(homeState({ hasNight: false, recCount: 0, hasPick: false })).toBe("no_games"));
  it("soirée sans recos : on attend la synchro, jamais les recos d'hier", () =>
    expect(homeState({ hasNight: true, recCount: 0, hasPick: false })).toBe("waiting_sync"));
  it("pick déjà posé", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: true })).toBe("picked"));
  it("à picker", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: false })).toBe("to_pick"));
});
