import { describe, expect, it } from "vitest";
import {
  LEAGUE_EXPECTED_WINS,
  TEAMS,
  isClosed,
  leagueWinsTotal,
  nameKey,
  standingsFromWins,
  validateWins,
} from "./pronos";

describe("TEAMS", () => {
  it("30 équipes, 15 par conférence, aucun doublon", () => {
    expect(TEAMS).toHaveLength(30);
    expect(TEAMS.filter((t) => t.conference === "Est")).toHaveLength(15);
    expect(TEAMS.filter((t) => t.conference === "Ouest")).toHaveLength(15);
    expect(new Set(TEAMS.map((t) => t.code)).size).toBe(30);
  });

  it("LEAGUE_EXPECTED_WINS = 1230 (82 matchs × 15 équipes par conférence)", () => {
    expect(LEAGUE_EXPECTED_WINS).toBe(1230);
  });
});

describe("nameKey", () => {
  it("ignore la casse et les espaces (bords + doublons internes)", () => {
    expect(nameKey("Jean Dupont")).toBe(nameKey("  jean   dupont  "));
    expect(nameKey("JEAN DUPONT")).toBe("jean dupont");
  });

  it("distingue des noms réellement différents", () => {
    expect(nameKey("Jean Dupont")).not.toBe(nameKey("Jean Dupond"));
  });
});

describe("validateWins", () => {
  it("accepte une carte partielle avec des valeurs entières 0-82", () => {
    const result = validateWins({ BOS: 60, LAL: 0, DEN: 82 });
    expect(result).toEqual({ ok: true, wins: { BOS: 60, LAL: 0, DEN: 82 } });
  });

  it("accepte une carte vide (saisie pas commencée)", () => {
    expect(validateWins({})).toEqual({ ok: true, wins: {} });
  });

  it("refuse une équipe inconnue", () => {
    const result = validateWins({ XXX: 41 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("XXX");
  });

  it("refuse une valeur non entière", () => {
    const result = validateWins({ BOS: 41.5 });
    expect(result.ok).toBe(false);
  });

  it("refuse une valeur hors bornes (négative ou > 82)", () => {
    expect(validateWins({ BOS: -1 }).ok).toBe(false);
    expect(validateWins({ BOS: 83 }).ok).toBe(false);
  });

  it("refuse un format qui n'est pas un objet", () => {
    expect(validateWins(null).ok).toBe(false);
    expect(validateWins("BOS:60").ok).toBe(false);
    expect(validateWins([1, 2, 3]).ok).toBe(false);
  });
});

describe("leagueWinsTotal", () => {
  it("somme les victoires saisies", () => {
    expect(leagueWinsTotal({ BOS: 60, LAL: 20 })).toBe(80);
  });

  it("0 pour une carte vide", () => {
    expect(leagueWinsTotal({})).toBe(0);
  });
});

describe("standingsFromWins", () => {
  const teams = [
    { code: "BOS", conference: "Est" as const },
    { code: "MIA", conference: "Est" as const },
    { code: "DEN", conference: "Ouest" as const },
    { code: "LAL", conference: "Ouest" as const },
  ];

  it("équipe absente de la carte = 0 victoire / 82 défaites", () => {
    const s = standingsFromWins({ BOS: 55 }, teams);
    expect(s.Est).toEqual([
      { team: "BOS", wins: 55, losses: 27 },
      { team: "MIA", wins: 0, losses: 82 },
    ]);
  });

  it("trie par victoires décroissantes, égalité par ordre alphabétique", () => {
    const s = standingsFromWins({ BOS: 50, MIA: 50, DEN: 40, LAL: 45 }, teams);
    expect(s.Est.map((r) => r.team)).toEqual(["BOS", "MIA"]); // égalité 50-50 → alpha
    expect(s.Ouest.map((r) => r.team)).toEqual(["LAL", "DEN"]); // 45 > 40
  });

  it("sépare bien les deux conférences", () => {
    const s = standingsFromWins({}, teams);
    expect(s.Est).toHaveLength(2);
    expect(s.Ouest).toHaveLength(2);
  });
});

describe("isClosed", () => {
  it("false avant l'échéance", () => {
    expect(isClosed(new Date("2026-10-20T00:00:00Z"), new Date("2026-10-20T23:00:00Z"))).toBe(false);
  });

  it("true pile à l'échéance", () => {
    const d = new Date("2026-10-20T23:00:00Z");
    expect(isClosed(d, d)).toBe(true);
  });

  it("true après l'échéance", () => {
    expect(isClosed(new Date("2026-10-21T00:00:00Z"), new Date("2026-10-20T23:00:00Z"))).toBe(true);
  });
});
