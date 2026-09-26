import { describe, expect, it } from "vitest";
import { addDays, deckDate, frDayMonth, frLongDate, parisTime, seasonForDate } from "./date";

describe("deckDate", () => {
  it("prend la date de Paris, pas celle de l'heure de l'Est", () => {
    // 2026-11-03 01:30 à Paris = 2026-11-02 19:30 à New York
    expect(deckDate(new Date("2026-11-03T00:30:00Z"))).toBe("2026-11-03");
  });
  it("juste avant minuit la veille du changement d'heure", () => {
    expect(deckDate(new Date("2026-10-24T22:30:00Z"))).toBe("2026-10-25");
  });
  it("gère le passage effectif à l'heure d'hiver (CET)", () => {
    expect(deckDate(new Date("2026-10-25T23:30:00Z"))).toBe("2026-10-26");
  });
});

describe("helpers", () => {
  it("addDays", () => {
    expect(addDays("2026-11-24", 14)).toBe("2026-12-08");
    expect(addDays("2026-03-28", 1)).toBe("2026-03-29");
  });
  it("seasonForDate", () => {
    expect(seasonForDate("2026-10-20")).toBe("2026-27");
    expect(seasonForDate("2027-04-15")).toBe("2026-27");
    expect(seasonForDate("2026-08-31")).toBe("2025-26");
  });
  it("formats FR", () => {
    expect(frDayMonth("2026-11-24")).toBe("24/11");
    expect(frLongDate("2026-11-24")).toBe("mardi 24 novembre");
    expect(parisTime("2026-11-24T23:00:00Z")).toBe("00:00");
  });
});
