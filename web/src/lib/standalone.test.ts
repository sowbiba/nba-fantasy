import { describe, expect, it } from "vitest";
import { STANDALONE_PREFIXES, isStandalonePath } from "./standalone";

describe("isStandalonePath (pages autonomes sans en-tête/navigation)", () => {
  it("liste les pages pronos 2026-27 et scores 2025-26", () => {
    expect(STANDALONE_PREFIXES).toEqual(["/pronos-26-27", "/scores-25-26"]);
  });

  it("reconnaît le préfixe exact et ses sous-chemins", () => {
    expect(isStandalonePath("/pronos-26-27")).toBe(true);
    expect(isStandalonePath("/pronos-26-27/")).toBe(true);
    expect(isStandalonePath("/pronos-26-27/11111111-1111-4111-8111-111111111111")).toBe(true);
    expect(isStandalonePath("/scores-25-26")).toBe(true);
    expect(isStandalonePath("/scores-25-26/abc")).toBe(true);
  });

  it("ne reconnaît pas un chemin qui ne fait que commencer pareil", () => {
    expect(isStandalonePath("/pronos-26-27x")).toBe(false);
    expect(isStandalonePath("/scores-25-266")).toBe(false);
  });

  it("laisse le reste de l'application avec son habillage", () => {
    expect(isStandalonePath("/")).toBe(false);
    expect(isStandalonePath("/games")).toBe(false);
    expect(isStandalonePath("/games/pronos-26-27")).toBe(false);
    expect(isStandalonePath(null)).toBe(false);
    expect(isStandalonePath(undefined)).toBe(false);
  });
});
