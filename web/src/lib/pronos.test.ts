import { describe, expect, it } from "vitest";
import {
  LEAGUE_EXPECTED_WINS,
  TEAMS,
  isClosed,
  leagueWinsTotal,
  nameKey,
  sanitizeName,
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

describe("sanitizeName", () => {
  it("retire les caractères de contrôle et de format (espaces de largeur nulle)", () => {
    expect(sanitizeName("Jean​Dupont")).toBe("JeanDupont"); // U+200B zero-width space
    expect(sanitizeName("Jean\u0000Dupont")).toBe("JeanDupont"); // caractère de contrôle
  });

  it("normalise NFKC (formes visuellement équivalentes)", () => {
    // U+FF21 (A pleine chasse) → "A" après NFKC.
    expect(sanitizeName("ＡBC")).toBe("ABC");
  });

  it("trim et réduit les espaces internes multiples", () => {
    expect(sanitizeName("  Jean   Dupont  ")).toBe("Jean Dupont");
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

  it("ignore les espaces de largeur nulle (contournement de doublon)", () => {
    expect(nameKey("Jean Dupont")).toBe(nameKey("Jean​ Dupont"));
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

  it("ne convertit aucune valeur : seul un vrai number JS est accepté (mineur 4)", () => {
    expect(validateWins({ BOS: "50" }).ok).toBe(false); // chaîne numérique
    expect(validateWins({ BOS: null }).ok).toBe(false);
    expect(validateWins({ BOS: "" }).ok).toBe(false);
    expect(validateWins({ BOS: true }).ok).toBe(false);
    expect(validateWins({ BOS: false }).ok).toBe(false);
    expect(validateWins({ BOS: undefined }).ok).toBe(false);
  });

  it("refuse plus de 30 équipes", () => {
    const wins = Object.fromEntries(TEAMS.map((t) => [t.code, 41]));
    expect(validateWins(wins)).toEqual({ ok: true, wins });
    const tooMany = { ...wins, EXTRA: 10 };
    const result = validateWins(tooMany);
    // EXTRA n'est de toute façon pas une équipe connue → refusé, mais la
    // garde sur le nombre de clés protège aussi une carte hypothétique de
    // 31 clés qui réutiliserait des codes connus (impossible avec des clés
    // d'objet uniques, mais défense en profondeur explicite).
    expect(result.ok).toBe(false);
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
