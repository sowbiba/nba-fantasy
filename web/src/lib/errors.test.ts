import { describe, expect, it } from "vitest";
import { pickErrorMessage } from "./errors";

describe("pickErrorMessage", () => {
  it("cooldown avec date de retour", () => {
    expect(pickErrorMessage({ code: "P0001", message: "player_unavailable:cooldown", details: "2026-11-24" }))
      .toBe("Joueur bloqué jusqu'au 24/11 (cooldown de 30 jours).");
  });
  it("réservation proche", () => {
    expect(pickErrorMessage({ code: "P0001", message: "player_unavailable:reserved_nearby" }))
      .toBe("Ce joueur est déjà réservé à moins de 30 jours de cette soirée.");
  });
  it("soirée inéligible", () => {
    expect(pickErrorMessage({ code: "P0001", message: "night_not_eligible:preseason" }))
      .toBe("Cette soirée ne compte pas pour la TTFL (présaison, play-in…).");
  });
  it("x2 déjà utilisé dans le mois", () => {
    expect(pickErrorMessage({ code: "23505", message: 'duplicate key value violates unique constraint "picks_x2_month"' }))
      .toBe("Tu as déjà utilisé ton x2 ce mois-ci.");
  });
  it("x2 hors fenêtre", () => {
    expect(pickErrorMessage({ code: "23514", message: 'new row violates check constraint "picks_x2_window"' }))
      .toBe("Le x2 n'existe qu'en saison régulière, de novembre à avril.");
  });
  it("défaut sans fuite du message brut", () => {
    expect(pickErrorMessage({ code: "XX000", message: "internal" })).toBe("Échec de l'enregistrement — réessaie.");
    expect(pickErrorMessage(null)).toBe("Échec de l'enregistrement — réessaie.");
  });
});
