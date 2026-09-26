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
  it("alerte blessure à tout moment avant la fermeture, une fois par statut", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: "Out" };
    const r = dueReminders({ now: at("2026-10-21T10:00:00Z"), night, pick, sent: new Set() });
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ kind: "injury", key: "7:Out" });
    expect(r[0].body).toContain("00:00");
    expect(dueReminders({ now: at("2026-10-21T11:00:00Z"), night, pick, sent: new Set(["injury|7:Out"]) })).toEqual([]);
  });
  it("Questionable ne déclenche rien", () => {
    const pick = { playerId: 7, name: "Jokic", injuryStatus: "Questionable" };
    expect(dueReminders({ now: at("2026-10-21T10:00:00Z"), night, pick, sent: new Set() })).toEqual([]);
  });
});
