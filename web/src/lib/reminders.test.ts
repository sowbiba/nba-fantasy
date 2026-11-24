import { describe, expect, it } from "vitest";
import { dueReminders } from "./reminders";

const night = { date: "2026-10-21", closing_at: "2026-10-21T22:00:00Z" }; // 00:00 Paris
const at = (iso: string) => new Date(iso);
const kinds = (r: ReturnType<typeof dueReminders>) => r.map((x) => x.kind);

describe("dueReminders", () => {
  it("rien avant −2 h", () => {
    expect(dueReminders({ now: at("2026-10-21T19:30:00Z"), night, pick: null, sent: new Set() })).toEqual([]);
  });
  it("−2 h sans pick", () => {
    expect(kinds(dueReminders({ now: at("2026-10-21T20:05:00Z"), night, pick: null, sent: new Set() }))).toEqual(["no_pick_2h"]);
  });
  it("−30 min : seulement le second rappel, même si le premier a été sauté", () => {
    expect(kinds(dueReminders({ now: at("2026-10-21T21:35:00Z"), night, pick: null, sent: new Set() }))).toEqual(["no_pick_30m"]);
  });
  it("déjà envoyé : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T20:05:00Z"), night, pick: null, sent: new Set(["no_pick_2h|"]) })).toEqual([]);
  });
  it("après la fermeture : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T22:00:00Z"), night, pick: null, sent: new Set() })).toEqual([]);
  });
  it("pas de soirée : rien", () => {
    expect(dueReminders({ now: at("2026-10-21T21:35:00Z"), night: null, pick: null, sent: new Set() })).toEqual([]);
  });
  it("pick posé : pas de rappel d'oubli", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: null };
    expect(dueReminders({ now: at("2026-10-21T21:35:00Z"), night, pick, sent: new Set() })).toEqual([]);
  });
});

// --- Vérification du deck sur 7 jours (24/11/2026) ---------------------------
import { deckAlerts, type DeckEntry } from "./reminders";

describe("deckAlerts", () => {
  const now = at("2026-11-24T10:00:00Z"); // 11:00 Paris
  const entry = (over: Partial<DeckEntry> = {}): DeckEntry => ({
    night: "2026-11-27", closingAt: "2026-11-27T23:00:00Z",
    pick: { playerId: 1, name: "Wembanyama", injuryStatus: null },
    proposal: { playerId: 1, name: "Wembanyama", expected: 45 },
    ...over,
  });

  it("deck conforme au moteur, joueur sain : rien", () => {
    expect(deckAlerts({ now, entries: [entry()], sent: new Set() })).toEqual([]);
  });

  it("pick signalé blessé : alerte avec la proposition du moteur", () => {
    const r = deckAlerts({ now, sent: new Set(), entries: [entry({
      pick: { playerId: 1, name: "Wembanyama", injuryStatus: "Day-To-Day" },
      proposal: { playerId: 2, name: "McDaniels", expected: 29.6 },
    })] });
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: "deck_injury", night: "2026-11-27", key: "1:Day-To-Day" });
    expect(r[0].title).toContain("27/11");
    expect(r[0].title).toContain("Wembanyama");
    expect(r[0].body).toContain("McDaniels");
    expect(r[0].body).toContain("29,6");
  });

  it("pick signalé mais gardé par le moteur : alerte sans remplaçant", () => {
    const r = deckAlerts({ now, sent: new Set(), entries: [entry({
      pick: { playerId: 1, name: "Wembanyama", injuryStatus: "Probable" },
    })] });
    expect(r).toHaveLength(1);
    expect(r[0].body).toContain("garde");
  });

  it("pick blessé sans proposition du moteur (x2 réservé) : ne dit pas qu'il le garde", () => {
    const r = deckAlerts({ now, sent: new Set(), entries: [entry({
      pick: { playerId: 1, name: "Wembanyama", injuryStatus: "Day-To-Day" }, proposal: null,
    })] });
    expect(r).toHaveLength(1);
    expect(r[0].body).not.toContain("garde");
    expect(r[0].body).toContain("Pas de proposition");
  });

  it("joueur sain mais le moteur propose un autre joueur : alerte de changement", () => {
    const r = deckAlerts({ now, sent: new Set(), entries: [entry({
      proposal: { playerId: 3, name: "SGA", expected: 45.7 },
    })] });
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: "deck_change", key: "1>3" });
    expect(r[0].body).toContain("SGA");
  });

  it("une seule fois par changement", () => {
    const e = entry({ proposal: { playerId: 3, name: "SGA", expected: 45.7 } });
    expect(deckAlerts({ now, entries: [e], sent: new Set(["2026-11-27|deck_change|1>3"]) })).toEqual([]);
  });

  it("pas de pick sur une soirée : rien (le rappel d'oubli s'en charge le soir même)", () => {
    expect(deckAlerts({ now, sent: new Set(), entries: [entry({ pick: null })] })).toEqual([]);
  });

  it("rien entre 00:00 et 07:00 Paris", () => {
    const e = entry({ proposal: { playerId: 3, name: "SGA", expected: 45.7 } });
    expect(deckAlerts({ now: at("2026-11-24T05:30:00Z"), entries: [e], sent: new Set() })).toEqual([]);
  });

  it("soirée déjà fermée : rien", () => {
    const e = entry({ closingAt: "2026-11-24T09:00:00Z", proposal: { playerId: 3, name: "SGA", expected: 45.7 } });
    expect(deckAlerts({ now, entries: [e], sent: new Set() })).toEqual([]);
  });
});
