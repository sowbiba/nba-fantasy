import { describe, expect, it } from "vitest";
import { isOwnerEmail } from "./owner";

describe("isOwnerEmail", () => {
  it("compare sans tenir compte de la casse", () => {
    expect(isOwnerEmail("Moi@Exemple.fr", "moi@exemple.fr")).toBe(true);
  });
  it("refuse sans session, sans propriétaire configuré ou avec un autre e-mail", () => {
    expect(isOwnerEmail(null, "moi@exemple.fr")).toBe(false);
    expect(isOwnerEmail("moi@exemple.fr", undefined)).toBe(false);
    expect(isOwnerEmail("autre@exemple.fr", "moi@exemple.fr")).toBe(false);
  });
});
