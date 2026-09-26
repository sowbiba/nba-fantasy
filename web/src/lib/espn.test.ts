import { describe, expect, it } from "vitest";
import { espnTricode, findEspnEvent, matchPlayerId, normalizeName, parseEspnBox } from "./espn";

describe("espn", () => {
  it("tricodes", () => {
    expect(["GS", "NY", "SA", "NO", "UTAH", "WSH", "BOS"].map(espnTricode))
      .toEqual(["GSW", "NYK", "SAS", "NOP", "UTA", "WAS", "BOS"]);
  });
  it("normalise les noms", () => {
    expect(normalizeName("Nikola Jokić")).toBe("nikola jokic");
    expect(normalizeName("Jaren Jackson Jr.")).toBe("jaren jackson");
    expect(normalizeName("P.J. Washington")).toBe("pj washington");
  });
  it("apparie sans confondre les homonymes", () => {
    const team = [{ id: 1, name: "Jalen Williams" }, { id: 2, name: "Jaylin Williams" }];
    expect(matchPlayerId("Jaylin Williams", team)).toBe(2);
    expect(matchPlayerId("Kenrich Williams", team)).toBeNull();
  });
  it("lit le box score par libellés", () => {
    const summary = { boxscore: { players: [{ team: { abbreviation: "GS" }, statistics: [{
      labels: ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"],
      athletes: [
        { athlete: { displayName: "Stephen Curry" }, starter: true, didNotPlay: false,
          stats: ["34", "30", "10-20", "5-11", "5-5", "4", "6", "3", "1", "0", "0", "4", "2", "+8"] },
        { athlete: { displayName: "Bench Guy" }, starter: false, didNotPlay: true, stats: [] },
      ] }] }] } };
    const rows = parseEspnBox(summary);
    expect(rows[0]).toMatchObject({ team: "GSW", name: "Stephen Curry", played: true, minutes: 34, pts: 30,
      fgm: 10, fga: 20, tpm: 5, tpa: 11, ftm: 5, fta: 5, reb: 4, ast: 6, tov: 3, stl: 1, blk: 0, fouls: 2 });
    expect(rows[1]).toMatchObject({ played: false, minutes: 0, pts: 0 });
  });
  it("trouve le match par équipes", () => {
    const sb = { events: [{ id: "401", status: { period: 2, displayClock: "5:12", type: { state: "in" } },
      competitions: [{ competitors: [
        { homeAway: "home", team: { abbreviation: "GS" }, score: "50" },
        { homeAway: "away", team: { abbreviation: "NY" }, score: "48" }] }] }] };
    expect(findEspnEvent(sb, "GSW", "NYK")).toEqual({ id: "401", state: "in", period: 2, clock: "5:12", homeScore: 50, awayScore: 48 });
    expect(findEspnEvent(sb, "BOS", "NYK")).toBeNull();
  });
});
