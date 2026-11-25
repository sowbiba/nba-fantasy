import { describe, expect, it } from "vitest";
import { buildDeckEntries } from "./deck-entries";

const today = "2026-11-24";
const nights = [{ date: today, closing_at: "2026-11-24T23:00:00Z" }, { date: "2026-11-27", closing_at: "2026-11-27T23:00:00Z" }];

describe("buildDeckEntries", () => {
  it("soir suivant : proposition = dernier plan (espérance = projection × p)", () => {
    const [, e] = buildDeckEntries({
      today, nights, tonightRecos: [],
      picks: [{ date: "2026-11-27", player_id: 1, players: { name: "Wembanyama", injury_status: "Day-To-Day" } }],
      plan: [{ night: "2026-11-27", player_id: 2, projection: 29.6, p_play: 1, players: { name: "McDaniels" } }],
    });
    expect(e.pick).toEqual({ playerId: 1, name: "Wembanyama", injuryStatus: "Day-To-Day" });
    expect(e.proposal).toEqual({ playerId: 2, name: "McDaniels", expected: 29.6 });
  });

  it("ce soir : un reco ne remplace le pick qu'au-delà de 3 points de gain net sur le deck", () => {
    const picks = [{ date: today, player_id: 1, players: { name: "Randle", injury_status: null } }];
    const recos = (gainSGA: number | null, gainHerro: number | null, vs = 1) => [
      { player_id: 2, rank: 1, estimated_score: 40.9, net_gain: gainSGA, net_gain_vs: vs, players: { name: "SGA" } },
      { player_id: 1, rank: 2, estimated_score: 33.2, net_gain: null, net_gain_vs: null, players: { name: "Randle" } },
      { player_id: 3, rank: 3, estimated_score: 37.0, net_gain: gainHerro, net_gain_vs: vs, players: { name: "Herro" } },
    ];
    const build = (r: ReturnType<typeof recos>) => buildDeckEntries({ today, nights, picks, plan: [], tonightRecos: r })[0];
    // 25/11/2026 : SGA +7,7 ce soir mais réservé le 02/12 → −4,8 sur le deck.
    expect(build(recos(-4.8, null)).proposal).toEqual({ playerId: 1, name: "Randle", expected: 33.2 });
    expect(build(recos(2.9, null)).proposal?.playerId).toBe(1);
    // Le meilleur gain net l'emporte, pas le rang du soir.
    expect(build(recos(4.1, 6.5)).proposal).toEqual({ playerId: 3, name: "Herro", expected: 37, netGain: 6.5 });
    // Gain calculé contre un autre pick (changé depuis la synchro) : ignoré.
    expect(build(recos(9, null, 7)).proposal?.playerId).toBe(1);
    // Pas de gain net (ancienne ligne) : on ne se fie plus à l'écart brut.
    expect(build(recos(null, null)).proposal?.playerId).toBe(1);
  });

  it("pick du soir absent des recos (écarté) : la reco n°1 est proposée", () => {
    const e = buildDeckEntries({ today, nights, plan: [],
      picks: [{ date: today, player_id: 1, players: [{ name: "Zion", injury_status: "Out" }] }],
      tonightRecos: [{ player_id: 2, rank: 1, estimated_score: 30, players: { name: "Sabonis" } }] })[0];
    expect(e.pick?.injuryStatus).toBe("Out");
    expect(e.proposal?.name).toBe("Sabonis");
  });

  it("soirée sans pick ni plan : entrée vide", () => {
    const [, e] = buildDeckEntries({ today, nights, picks: [], plan: [], tonightRecos: [] });
    expect(e).toEqual({ night: "2026-11-27", closingAt: "2026-11-27T23:00:00Z", pick: null, proposal: null });
  });
});
