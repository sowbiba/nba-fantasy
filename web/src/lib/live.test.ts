import { describe, expect, it } from "vitest";
import { liveDates, mergeLive, needsLivePolling, parseEspnScoreboardLive } from "./live";
import type { Game } from "@/types";

const event = (home: string, away: string, state: string, hs: string, as: string, period = 3, clock = "4:12") => ({
  id: "1",
  status: { period, displayClock: clock, type: { state } },
  competitions: [{ competitors: [
    { homeAway: "home", team: { abbreviation: home }, score: hs },
    { homeAway: "away", team: { abbreviation: away }, score: as },
  ] }],
});

const game = (over: Partial<Game> = {}): Game => ({
  id: "g1", date: "2026-11-06", home_team: "CHA", away_team: "BOS", tip_off: "2026-11-07T00:00:00+00:00",
  series_id: null, game_number: null, status: "scheduled", home_score: null, away_score: null,
  game_type: "regular", ...over,
} as Game);

describe("parseEspnScoreboardLive", () => {
  it("lit état, scores et horloge, avec les tricodes NBA", () => {
    const rows = parseEspnScoreboardLive({ events: [event("GS", "NY", "in", "79", "45")] });
    expect(rows).toEqual([{ home: "GSW", away: "NYK", state: "in", homeScore: 79, awayScore: 45, period: 3, clock: "4:12" }]);
  });

  it("payload invalide : liste vide", () => {
    expect(parseEspnScoreboardLive(null)).toEqual([]);
  });
});

describe("mergeLive", () => {
  const live = [{ home: "CHA", away: "BOS", state: "in", homeScore: 45, awayScore: 79, period: 3, clock: "4:12" }];

  it("match en cours : statut live, score et quart-temps", () => {
    const [g] = mergeLive([game()], live);
    expect(g.status).toBe("live");
    expect([g.home_score, g.away_score]).toEqual([45, 79]);
    expect(g.live_detail).toBe("Q3 4:12");
  });

  it("match terminé côté ESPN : final avec le score ESPN (corrige un score de nuit périmé)", () => {
    const [g] = mergeLive([game({ status: "final", home_score: 45, away_score: 79 })],
      [{ ...live[0], state: "post", homeScore: 80, awayScore: 119 }]);
    expect(g.status).toBe("final");
    expect([g.home_score, g.away_score]).toEqual([80, 119]);
  });

  it("prolongation et mi-temps lisibles", () => {
    expect(mergeLive([game()], [{ ...live[0], period: 5, clock: "2:00" }])[0].live_detail).toBe("OT 2:00");
    expect(mergeLive([game()], [{ ...live[0], period: 2, clock: "0.0" }])[0].live_detail).toBe("Mi-temps");
  });

  it("match pas encore commencé ou absent d'ESPN : inchangé", () => {
    const g = game();
    expect(mergeLive([g], [{ ...live[0], state: "pre" }])[0]).toBe(g);
    expect(mergeLive([g], [])[0]).toBe(g);
  });
});

describe("needsLivePolling", () => {
  const now = new Date("2026-11-07T01:00:00Z");
  it("vrai si un match a commencé et n'est pas final", () => {
    expect(needsLivePolling([game()], now)).toBe(true);
  });
  it("faux si tout est terminé, pas commencé, ou commencé il y a plus de 6 h", () => {
    expect(needsLivePolling([game({ status: "final" })], now)).toBe(false);
    expect(needsLivePolling([game({ tip_off: "2026-11-07T03:00:00Z" })], now)).toBe(false);
    expect(needsLivePolling([game({ tip_off: "2026-11-06T18:00:00Z" })], now)).toBe(false);
  });
});

describe("liveDates", () => {
  it("dates ESPN (AAAAMMJJ) des matchs à suivre, sans doublon", () => {
    const now = new Date("2026-11-07T01:00:00Z");
    expect(liveDates([game(), game({ id: "g2" }), game({ id: "g3", status: "final" })], now)).toEqual(["20261106"]);
  });
});
