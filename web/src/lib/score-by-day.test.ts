import { describe, expect, it } from "vitest";
import { distinctNights, neighbors, parseDayParams, toDayRows, type DayLogInput } from "./score-by-day";

const NIGHTS = ["2025-10-21", "2025-10-22", "2025-10-24"];
const TEAMS = ["BOS", "LAL"];

describe("parseDayParams", () => {
  it("date connue et équipe connue (casse ignorée)", () => {
    expect(parseDayParams({ date: "2025-10-22", team: "lal" }, NIGHTS, TEAMS)).toEqual({ date: "2025-10-22", team: "LAL" });
  });

  it("date absente, inconnue ou mal formée → dernière soirée ; équipe inconnue → toutes", () => {
    for (const date of [undefined, "2025-10-23", "hier", "2025-10-22'--"]) {
      expect(parseDayParams({ date, team: "XXX" }, NIGHTS, TEAMS)).toEqual({ date: "2025-10-24", team: null });
    }
  });

  it("aucune soirée → date null", () => {
    expect(parseDayParams({}, [], TEAMS).date).toBeNull();
  });
});

describe("neighbors / distinctNights", () => {
  it("précédente et suivante, null aux extrémités", () => {
    expect(neighbors(NIGHTS, "2025-10-22")).toEqual({ prev: "2025-10-21", next: "2025-10-24" });
    expect(neighbors(NIGHTS, "2025-10-21")).toEqual({ prev: null, next: "2025-10-22" });
    expect(neighbors(NIGHTS, "2025-10-24")).toEqual({ prev: "2025-10-22", next: null });
    expect(neighbors(NIGHTS, null)).toEqual({ prev: null, next: null });
  });

  it("dédoublonne et trie", () => {
    expect(distinctNights(["2025-10-22", "2025-10-21", "2025-10-22"])).toEqual(["2025-10-21", "2025-10-22"]);
  });
});

function log(p: Partial<DayLogInput>): DayLogInput {
  return {
    player_id: 1,
    team: "BOS",
    is_home: true,
    minutes: 30,
    pts: 20,
    reb: 5,
    ast: 4,
    stl: 1,
    blk: 0,
    tov: 2,
    fgm: 8,
    fga: 15,
    tpm: 2,
    tpa: 6,
    ftm: 2,
    fta: 2,
    ttfl_score: 30,
    players: { name: "Joueur" },
    games: { home_team: "BOS", away_team: "LAL", game_type: "regular" },
    ...p,
  };
}

describe("toDayRows", () => {
  it("adversaire, domicile/extérieur, tirs réussis et tentés séparés", () => {
    const [home] = toDayRows([log({})]);
    expect(home).toMatchObject({ opponent: "LAL", home: true, fgm: 8, fga: 15, tpm: 2, tpa: 6, ftm: 2, fta: 2 });
    const [away] = toDayRows([log({ team: "LAL" })]);
    expect(away).toMatchObject({ opponent: "BOS", home: false });
  });

  it("tri par TTFL décroissant puis nom ; DNP, match absent et types hors jeu écartés", () => {
    const rows = toDayRows([
      log({ player_id: 1, ttfl_score: 20, players: { name: "Zed" } }),
      log({ player_id: 2, ttfl_score: 45, players: { name: "Bob" } }),
      log({ player_id: 3, ttfl_score: 20, players: { name: "Abe" } }),
      log({ player_id: 4, minutes: 0 }),
      log({ player_id: 5, games: null }),
      log({ player_id: 6, games: { home_team: "BOS", away_team: "LAL", game_type: "preseason" } }),
      log({ player_id: 7, ttfl_score: -3, games: { home_team: "BOS", away_team: "LAL", game_type: "cup_final" } }),
    ]);
    expect(rows.map((r) => r.playerId)).toEqual([2, 3, 1, 7]);
  });

  it("nom manquant → identifiant", () => {
    expect(toDayRows([log({ player_id: 42, players: null })])[0].name).toBe("#42");
  });
});
