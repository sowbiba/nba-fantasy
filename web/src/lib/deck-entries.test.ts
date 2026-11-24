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

  it("ce soir : la reco n°1 ne remplace le pick qu'au-delà de 3 points", () => {
    const picks = [{ date: today, player_id: 1, players: { name: "Murray", injury_status: null } }];
    const close = buildDeckEntries({ today, nights, picks, plan: [], tonightRecos: [
      { player_id: 2, rank: 1, estimated_score: 42, players: { name: "Autre" } },
      { player_id: 1, rank: 2, estimated_score: 40.6, players: { name: "Murray" } },
    ] })[0];
    expect(close.proposal?.playerId).toBe(1);
    const far = buildDeckEntries({ today, nights, picks, plan: [], tonightRecos: [
      { player_id: 2, rank: 1, estimated_score: 45, players: { name: "Autre" } },
      { player_id: 1, rank: 2, estimated_score: 40.6, players: { name: "Murray" } },
    ] })[0];
    expect(far.proposal).toEqual({ playerId: 2, name: "Autre", expected: 45 });
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
