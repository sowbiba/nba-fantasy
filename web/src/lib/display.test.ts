import { describe, expect, it } from "vitest";
import {
  formatPointDiff,
  homeState,
  isClosed,
  pickPoints,
  recMeta,
  sortStandings,
  standingsTint,
  standingsZone,
  streakScore,
  topDefender,
  winPct,
  winPctPair,
  x2Hint,
  x2HintText,
} from "./display";
import type { StandingsRow } from "@/types";

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

describe("formatPointDiff", () => {
  it("positif : signe +", () => expect(formatPointDiff(7.53)).toBe("+7.5"));
  it("négatif : signe -", () => expect(formatPointDiff(-3.24)).toBe("-3.2"));
  it("zéro exact : pas de signe", () => expect(formatPointDiff(0)).toBe("0.0"));
  it("arrondit à zéro : jamais -0.0", () => {
    expect(formatPointDiff(-0.04)).toBe("0.0");
    expect(formatPointDiff(0.04)).toBe("0.0");
  });
  it("valeur en chaîne (PostgREST numeric) : coercée", () => expect(formatPointDiff("6.3")).toBe("+6.3"));
});

describe("streakScore", () => {
  it("série de victoires : positif, la longueur", () => {
    expect(streakScore("V3")).toBe(3);
    expect(streakScore("V1")).toBe(1);
  });
  it("série de défaites : négatif, la longueur", () => {
    expect(streakScore("D1")).toBe(-1);
    expect(streakScore("D5")).toBe(-5);
  });
  it("pas de série : 0", () => expect(streakScore("")).toBe(0));
  it("format inattendu : 0, ne plante pas", () => {
    expect(streakScore("X2")).toBe(0);
    expect(streakScore("V")).toBe(0);
    expect(streakScore("2")).toBe(0);
  });
});

describe("sortStandings", () => {
  function row(overrides: Partial<StandingsRow>): StandingsRow {
    return {
      season: "2026-27",
      conference: "Est",
      team: "AAA",
      wins: 0,
      losses: 0,
      pct: 0,
      games_behind: 0,
      home_wins: 0,
      home_losses: 0,
      away_wins: 0,
      away_losses: 0,
      last10_wins: 0,
      last10_losses: 0,
      streak: "",
      rank: 1,
      point_diff: 0,
      ...overrides,
    };
  }

  const rows = [
    row({ team: "A", rank: 1, wins: 10, losses: 2, pct: 0.833, games_behind: 0, last10_wins: 7, streak: "V2", point_diff: 8.5 }),
    row({ team: "B", rank: 2, wins: 8, losses: 4, pct: 0.667, games_behind: 2, last10_wins: 9, streak: "D1", point_diff: -1.2 }),
    row({ team: "C", rank: 3, wins: 6, losses: 6, pct: 0.5, games_behind: 4, last10_wins: 3, streak: "V5", point_diff: 3.0 }),
  ];

  it("ne mute pas le tableau d'entrée", () => {
    const copy = [...rows];
    sortStandings(rows, "pct", "asc");
    expect(rows).toEqual(copy);
  });

  it("clé rank (défaut) : ordre officiel", () => {
    expect(sortStandings(rows, "rank", "asc").map((r) => r.team)).toEqual(["A", "B", "C"]);
    expect(sortStandings(rows, "rank", "desc").map((r) => r.team)).toEqual(["C", "B", "A"]);
  });

  it("clé pct : % décroissant en premier appui", () => {
    expect(sortStandings(rows, "pct", "asc").map((r) => r.team)).toEqual(["A", "B", "C"]);
    expect(sortStandings(rows, "pct", "desc").map((r) => r.team)).toEqual(["C", "B", "A"]);
  });

  it("clé wins : victoires décroissantes en premier appui", () => {
    expect(sortStandings(rows, "wins", "asc").map((r) => r.team)).toEqual(["A", "B", "C"]);
  });

  it("clé losses : défaites croissantes en premier appui (moins = mieux)", () => {
    expect(sortStandings(rows, "losses", "asc").map((r) => r.team)).toEqual(["A", "B", "C"]);
  });

  it("clé games_behind : écart croissant en premier appui (0 = mieux)", () => {
    expect(sortStandings(rows, "games_behind", "asc").map((r) => r.team)).toEqual(["A", "B", "C"]);
  });

  it("clé last10 : victoires des 10 derniers décroissantes en premier appui", () => {
    expect(sortStandings(rows, "last10", "asc").map((r) => r.team)).toEqual(["B", "A", "C"]);
  });

  it("clé point_diff : écart décroissant en premier appui", () => {
    expect(sortStandings(rows, "point_diff", "asc").map((r) => r.team)).toEqual(["A", "C", "B"]);
    expect(sortStandings(rows, "point_diff", "desc").map((r) => r.team)).toEqual(["B", "C", "A"]);
  });

  it("clé streak : séries de victoires d'abord (la plus longue en tête), puis vide, puis défaites (la plus courte en tête)", () => {
    const withEmpty = [...rows, row({ team: "D", rank: 4, streak: "" })];
    expect(sortStandings(withEmpty, "streak", "asc").map((r) => r.team)).toEqual(["C", "A", "D", "B"]);
  });

  it("clé streak inversée (2e appui) : défaites d'abord (la plus longue en tête), puis vide, puis victoires (la plus courte en tête)", () => {
    const withEmpty = [...rows, row({ team: "D", rank: 4, streak: "" })];
    expect(sortStandings(withEmpty, "streak", "desc").map((r) => r.team)).toEqual(["B", "D", "A", "C"]);
  });

  it("clé force : cote décroissante en premier appui, absente toujours en fin de liste dans les deux sens", () => {
    const ratings = { A: 1500, B: 1600 }; // C absent (pas dans team_elo)
    expect(sortStandings(rows, "force", "asc", ratings).map((r) => r.team)).toEqual(["B", "A", "C"]);
    expect(sortStandings(rows, "force", "desc", ratings).map((r) => r.team)).toEqual(["A", "B", "C"]);
  });

  it("clé force sans ratings du tout : ordre stable par rang", () => {
    expect(sortStandings(rows, "force", "asc", null).map((r) => r.team)).toEqual(["A", "B", "C"]);
  });

  it("égalité : départage stable par rang officiel, jamais mélangé au 2e appui", () => {
    const tied = [
      row({ team: "X", rank: 5, wins: 5 }),
      row({ team: "Y", rank: 2, wins: 5 }),
      row({ team: "Z", rank: 8, wins: 5 }),
    ];
    expect(sortStandings(tied, "wins", "asc").map((r) => r.team)).toEqual(["Y", "X", "Z"]);
    expect(sortStandings(tied, "wins", "desc").map((r) => r.team)).toEqual(["Y", "X", "Z"]);
  });

  it("valeurs en chaîne (PostgREST numeric) : coercées, pas d'ordre lexical", () => {
    const stringy = [
      row({ team: "P", rank: 1, pct: "0.9" as unknown as number, point_diff: "10.0" as unknown as number }),
      row({ team: "Q", rank: 2, pct: "0.5" as unknown as number, point_diff: "2.0" as unknown as number }),
    ];
    expect(sortStandings(stringy, "pct", "asc").map((r) => r.team)).toEqual(["P", "Q"]);
    expect(sortStandings(stringy, "point_diff", "asc").map((r) => r.team)).toEqual(["P", "Q"]);
  });
});
