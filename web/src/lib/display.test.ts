import { describe, expect, it } from "vitest";
import { homeState, isClosed, pickPoints, recMeta, standingsTint, standingsZone, topDefender, winPct, winPctPair, x2Hint, x2HintText } from "./display";

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

describe("topDefender", () => {
  it("prend le défenseur le plus présent et sa part", () => {
    expect(topDefender([
      { def_player_name: "Davis", minutes: 10, points: 12, games: 1 },
      { def_player_name: "James", minutes: 5, points: 5, games: 1 },
    ])).toEqual({ name: "Davis", share: 67, per36: 43.2, games: 1 });
  });
  it("rien sous 5 minutes d'échantillon", () => {
    expect(topDefender([{ def_player_name: "Davis", minutes: 4, points: 3, games: 1 }])).toBeNull();
    expect(topDefender([])).toBeNull();
  });
});

describe("isClosed", () => {
  it("pile à l'heure de fermeture : fermée", () =>
    expect(isClosed("2026-11-24T23:00:00Z", new Date("2026-11-24T23:00:00Z"))).toBe(true));
  it("une seconde avant : encore ouverte", () =>
    expect(isClosed("2026-11-24T23:00:00Z", new Date("2026-11-24T22:59:59Z"))).toBe(false));
  it("pas de closingAt connu : ne bloque pas", () => {
    expect(isClosed(null, new Date("2026-11-24T23:00:00Z"))).toBe(false);
    expect(isClosed(undefined, new Date("2026-11-24T23:00:00Z"))).toBe(false);
  });
});

describe("winPctPair", () => {
  it("l'extérieur = 100 − l'arrondi du domicile, jamais un arrondi indépendant de 1 - p", () => {
    // Arrondis indépendants donneraient 36 % / 65 % (36 + 65 = 101) : ici
    // l'extérieur doit être 100 − 36 = 64 % (M-10, review finale L3a).
    expect(winPctPair(0.355)).toEqual({ home: "36 %", away: "64 %" });
  });
  it("la paire somme toujours à 100", () => {
    for (const p of [0.0, 0.001, 0.125, 0.355, 0.5, 0.645, 0.999, 1.0]) {
      const { home, away } = winPctPair(p);
      expect(parseInt(home) + parseInt(away)).toBe(100);
    }
  });
});

describe("x2Hint", () => {
  const base = { planIsX2: true, planPlayerId: 7, pickPlayerId: null, pickIsX2: false, x2Allowed: true };
  it("sans pick, le plan suggère le x2 ce soir : pose", () => expect(x2Hint(base)).toBe("pose"));
  it("pick = joueur du plan, x2 pas encore posé : pose_sur_pick", () =>
    expect(x2Hint({ ...base, pickPlayerId: 7 })).toBe("pose_sur_pick"));
  it("pick = joueur du plan, x2 déjà posé : deja", () =>
    expect(x2Hint({ ...base, pickPlayerId: 7, pickIsX2: true })).toBe("deja"));
  it("pick ≠ joueur du plan (plan d'avant le pick) : rien à afficher", () => {
    expect(x2Hint({ ...base, pickPlayerId: 8 })).toBeNull();
    expect(x2Hint({ ...base, pickPlayerId: 8, pickIsX2: true })).toBeNull();
  });
  it("mois interdit (x2Allowed false) : rien à afficher même si le plan suggère", () =>
    expect(x2Hint({ ...base, x2Allowed: false })).toBeNull());
  it("le plan ne suggère pas le x2 ce soir : rien à afficher", () =>
    expect(x2Hint({ ...base, planIsX2: false, pickPlayerId: 7 })).toBeNull());
});

describe("x2HintText", () => {
  it("sans pick : nomme le joueur du plan", () =>
    expect(x2HintText("pose", "Nikola Jokic")).toBe("Le plan suggère un x2 ce soir (sur Nikola Jokic)."));
  it("nom manquant : phrase sans nom, jamais undefined", () => {
    for (const name of [undefined, null, ""]) {
      const text = x2HintText("pose", name);
      expect(text).toBe("Le plan suggère un x2 ce soir.");
      expect(text).not.toContain("undefined");
    }
  });
  it("sur le pick : ne prétend rien d'autre que la décision du plan sur ce pick", () => {
    expect(x2HintText("pose_sur_pick", "X")).toBe("Le plan suggère le x2 ce soir sur ton pick : active-le ci-dessous.");
    expect(x2HintText("pose_sur_pick", "X")).not.toContain("reste valable");
  });
  it("déjà posé", () => expect(x2HintText("deja")).toBe("x2 activé sur ton pick, comme le suggère le plan pour ce soir."));
});

describe("winPct", () => {
  it("arrondit à l'entier, espace avant %", () => {
    expect(winPct(0.64)).toBe("64 %");
    expect(winPct(0.355)).toBe("36 %");
  });
  it("bornes 0 et 1", () => {
    expect(winPct(0)).toBe("0 %");
    expect(winPct(1)).toBe("100 %");
  });
});

describe("homeState", () => {
  it("pas de soirée", () => expect(homeState({ hasNight: false, recCount: 0, hasPick: false })).toBe("no_games"));
  it("soirée sans recos : on attend la synchro, jamais les recos d'hier", () =>
    expect(homeState({ hasNight: true, recCount: 0, hasPick: false })).toBe("waiting_sync"));
  it("pick déjà posé", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: true })).toBe("picked"));
  it("à picker", () => expect(homeState({ hasNight: true, recCount: 12, hasPick: false })).toBe("to_pick"));
});

describe("standingsZone", () => {
  it.each([1, 3, 6])("place %i : playoffs", (rank) => expect(standingsZone(rank)).toBe("playoffs"));
  it.each([7, 8, 10])("place %i : play-in", (rank) => expect(standingsZone(rank)).toBe("playin"));
  it.each([0, -1, 11, 15])("place %i : aucune zone", (rank) => expect(standingsZone(rank)).toBeNull());
});

describe("standingsTint", () => {
  it("dégressif sur 1-6, jamais fort", () => {
    expect(standingsTint(1)).toBeGreaterThan(standingsTint(6));
    expect(standingsTint(1)).toBeLessThanOrEqual(0.07);
  });
  it("plus léger sur 7-10 que sur 1-6", () => {
    expect(standingsTint(7)).toBeLessThan(standingsTint(6));
    expect(standingsTint(10)).toBeGreaterThanOrEqual(0);
  });
  it("nul au-delà de la 10e place", () => {
    expect(standingsTint(11)).toBe(0);
    expect(standingsTint(15)).toBe(0);
  });
});
