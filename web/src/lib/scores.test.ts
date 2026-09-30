import { describe, expect, it } from "vitest";
import {
  DEFAULT_MIN_GAMES,
  GAME_TYPES,
  ScoreRow,
  buildScoresCsv,
  csvField,
  csvFilename,
  decimalComma,
  parseScoresParams,
  sortScores,
} from "./scores";

const TEAMS = ["ATL", "BOS", "NYK"] as const;

function row(overrides: Partial<ScoreRow> = {}): ScoreRow {
  return {
    playerId: 1,
    name: "Jayson Tatum",
    team: "BOS",
    games: 40,
    avgTtfl: 45.5,
    totalTtfl: 1820,
    topScore: 78,
    topDate: "2025-11-03",
    topOpponent: "NYK",
    ...overrides,
  };
}

describe("GAME_TYPES", () => {
  it("expose les deux types avec leurs libellés français", () => {
    expect(GAME_TYPES).toEqual([
      { value: "regular", label: "Saison régulière" },
      { value: "playoffs", label: "Playoffs" },
    ]);
  });
});

describe("parseScoresParams", () => {
  it("valeurs par défaut quand rien n'est fourni", () => {
    const result = parseScoresParams({}, TEAMS);
    expect(result.invalid).toEqual([]);
    expect(result.params).toEqual({
      type: "regular",
      team: null,
      minGames: DEFAULT_MIN_GAMES.regular,
      sortKey: "avg",
      sortDir: "desc",
    });
  });

  it("accepte des paramètres valides", () => {
    const result = parseScoresParams(
      { type: "playoffs", team: "nyk", min: "10", sort: "top", dir: "asc" },
      TEAMS,
    );
    expect(result.invalid).toEqual([]);
    expect(result.params).toEqual({
      type: "playoffs",
      team: "NYK",
      minGames: 10,
      sortKey: "top",
      sortDir: "asc",
    });
  });

  it("retombe sur le minimum par défaut du type quand min est absent", () => {
    expect(parseScoresParams({ type: "playoffs" }, TEAMS).params.minGames).toBe(
      DEFAULT_MIN_GAMES.playoffs,
    );
  });

  it("signale et corrige un type invalide", () => {
    const result = parseScoresParams({ type: "n_importe_quoi" }, TEAMS);
    expect(result.invalid).toContain("type");
    expect(result.params.type).toBe("regular");
  });

  it("signale et corrige une équipe inconnue", () => {
    const result = parseScoresParams({ team: "ZZZ" }, TEAMS);
    expect(result.invalid).toContain("team");
    expect(result.params.team).toBeNull();
  });

  it("signale et corrige un minimum hors bornes ou non entier", () => {
    for (const bad of ["0", "83", "-1", "abc", "3.5", ""]) {
      const result = parseScoresParams({ min: bad }, TEAMS);
      if (bad === "") {
        // Absent/vide : pas une erreur, juste le défaut.
        expect(result.invalid).not.toContain("min");
      } else {
        expect(result.invalid).toContain("min");
      }
      expect(result.params.minGames).toBe(DEFAULT_MIN_GAMES.regular);
    }
  });

  it("accepte les bornes 1 et 82", () => {
    expect(parseScoresParams({ min: "1" }, TEAMS).params.minGames).toBe(1);
    expect(parseScoresParams({ min: "82" }, TEAMS).params.minGames).toBe(82);
  });

  it("signale et corrige un tri ou une direction invalides", () => {
    const result = parseScoresParams({ sort: "xx", dir: "yy" }, TEAMS);
    expect(result.invalid).toEqual(expect.arrayContaining(["sort", "dir"]));
    expect(result.params.sortKey).toBe("avg");
    expect(result.params.sortDir).toBe("desc");
  });

  it("prend la première valeur si un paramètre est répété (tableau)", () => {
    const result = parseScoresParams({ type: ["playoffs", "regular"] }, TEAMS);
    expect(result.params.type).toBe("playoffs");
  });
});

describe("sortScores", () => {
  const rows = [
    row({ playerId: 1, name: "B", avgTtfl: 30, topScore: 60 }),
    row({ playerId: 2, name: "A", avgTtfl: 50, topScore: 40 }),
    row({ playerId: 3, name: "C", avgTtfl: 50, topScore: 90 }),
  ];

  it("trie par moyenne décroissante par défaut", () => {
    const sorted = sortScores(rows, "avg", "desc");
    expect(sorted.map((r) => r.playerId)).toEqual([3, 2, 1]);
  });

  it("trie par moyenne croissante", () => {
    const noTies = [
      row({ playerId: 1, name: "B", avgTtfl: 30, topScore: 60 }),
      row({ playerId: 2, name: "A", avgTtfl: 50, topScore: 40 }),
      row({ playerId: 3, name: "C", avgTtfl: 70, topScore: 90 }),
    ];
    const sorted = sortScores(noTies, "avg", "asc");
    expect(sorted.map((r) => r.playerId)).toEqual([1, 2, 3]);
  });

  it("trie par top score décroissant", () => {
    const sorted = sortScores(rows, "top", "desc");
    expect(sorted.map((r) => r.playerId)).toEqual([3, 1, 2]);
  });

  it("départage une égalité de moyenne par le top score puis le nom", () => {
    // playerId 2 (avg 50, top 40) vs 3 (avg 50, top 90) : à moyenne égale,
    // le top score le plus haut passe devant, même en tri croissant sur la
    // moyenne (le départage n'est jamais inversé par `dir`).
    const sorted = sortScores(rows, "avg", "asc");
    const [a2, a3] = [sorted.findIndex((r) => r.playerId === 2), sorted.findIndex((r) => r.playerId === 3)];
    expect(a3).toBeLessThan(a2);
  });

  it("ne mute pas le tableau d'entrée", () => {
    const copy = [...rows];
    sortScores(rows, "avg", "desc");
    expect(rows).toEqual(copy);
  });
});

describe("decimalComma", () => {
  it("formate un nombre avec une virgule et une décimale", () => {
    expect(decimalComma(45.5)).toBe("45,5");
    expect(decimalComma(45)).toBe("45,0");
    expect(decimalComma(45.04)).toBe("45,0");
    expect(decimalComma(45.06)).toBe("45,1");
  });

  it("gère les chaînes numériques (PostgREST peut renvoyer un numeric en string)", () => {
    expect(decimalComma("45.5" as unknown as number)).toBe("45,5");
  });
});

describe("csvField (échappement CSV + garde anti-injection de formule)", () => {
  it("laisse un champ simple inchangé", () => {
    expect(csvField("Jayson Tatum")).toBe("Jayson Tatum");
  });

  it("met entre guillemets un champ contenant le séparateur ;", () => {
    expect(csvField("Boston;Celtics")).toBe('"Boston;Celtics"');
  });

  it("met entre guillemets et double les guillemets internes", () => {
    expect(csvField('Le "Joker"')).toBe('"Le ""Joker"""');
  });

  it("met entre guillemets un champ contenant un retour à la ligne", () => {
    expect(csvField("a\nb")).toBe('"a\nb"');
    expect(csvField("a\rb")).toBe('"a\rb"');
  });

  it("neutralise l'injection de formule (= + - @) par une apostrophe", () => {
    expect(csvField("=CMD()")).toBe("'=CMD()");
    expect(csvField("+1")).toBe("'+1");
    expect(csvField("-1")).toBe("'-1");
    expect(csvField("@SUM(A1)")).toBe("'@SUM(A1)");
  });

  it("combine garde anti-formule et guillemets", () => {
    expect(csvField('=A1;"x"')).toBe(`"'=A1;""x"""`);
  });

  it("ne touche pas un champ qui ne commence pas par un caractère dangereux", () => {
    expect(csvField("Team-A")).toBe("Team-A");
  });
});

describe("buildScoresCsv", () => {
  it("commence par le BOM UTF-8", () => {
    const csv = buildScoresCsv([]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
  });

  it("a un en-tête en français séparé par ;", () => {
    const csv = buildScoresCsv([]);
    const firstLine = csv.slice(1).split("\r\n")[0];
    expect(firstLine).toBe("Joueur;Équipe;Matchs;Moyenne TTFL;Top;Date du top;Adversaire du top");
  });

  it("formate une ligne de données (virgule décimale, date jj/mm)", () => {
    const csv = buildScoresCsv([row()]);
    const lines = csv.slice(1).split("\r\n");
    expect(lines[1]).toBe("Jayson Tatum;BOS;40;45,5;78;03/11;NYK");
  });

  it("échappe un nom de joueur dangereux (défense en profondeur)", () => {
    const csv = buildScoresCsv([row({ name: "=HYPERLINK(\"http://evil\")" })]);
    const lines = csv.slice(1).split("\r\n");
    expect(lines[1].startsWith("\"'=HYPERLINK")).toBe(true);
  });

  it("ne corrompt pas une moyenne ou un top score négatifs (la garde anti-formule ne s'applique qu'aux champs texte)", () => {
    // Un score TTFL peut être négatif (tirs manqués/pertes de balle en fin
    // de banc) : le `-` en tête est un signe, pas une formule à neutraliser.
    const csv = buildScoresCsv([row({ avgTtfl: -3.5, topScore: -2 })]);
    const lines = csv.slice(1).split("\r\n");
    expect(lines[1]).toBe("Jayson Tatum;BOS;40;-3,5;-2;03/11;NYK");
  });
});

describe("csvFilename", () => {
  it("sans équipe", () => {
    expect(csvFilename("regular", null)).toBe("scores-ttfl-2025-26-regular.csv");
    expect(csvFilename("playoffs", null)).toBe("scores-ttfl-2025-26-playoffs.csv");
  });

  it("avec équipe (en minuscules)", () => {
    expect(csvFilename("regular", "NYK")).toBe("scores-ttfl-2025-26-regular-nyk.csv");
  });
});
