import { describe, expect, it } from "vitest";
import { imageSafeName, isImageSafeChar } from "./image-text";

describe("imageSafeName (nom affiché dans l'image : seulement des glyphes des polices locales)", () => {
  it("garde ASCII, Latin-1 et la ponctuation typographique couverte", () => {
    expect(imageSafeName("Jean-Noël O’Neil « Élan » — ÀÇÉÎØßÿ · €…")).toBe("Jean-Noël O’Neil « Élan » — ÀÇÉÎØßÿ · €…");
    expect(imageSafeName("Œdipe & cœur")).toBe("Œdipe & cœur");
  });

  it("réduit les lettres accentuées hors police à leur lettre de base (Latin étendu)", () => {
    expect(imageSafeName("Nikola Jokić")).toBe("Nikola Jokic");
    expect(imageSafeName("Dončić Šarić Őz Ștefan")).toBe("Doncic Saric Oz Stefan");
    expect(imageSafeName("Łukasz Đorđe")).toBe("Lukasz Dorde");
  });

  it("retire emoji, écritures non latines et caractères invisibles, puis resserre les espaces", () => {
    expect(imageSafeName("🏀 Jean  🔥 Dupont ✨")).toBe("Jean Dupont");
    expect(imageSafeName("Jean 李 Dupont")).toBe("Jean Dupont");
    expect(imageSafeName("Je​an")).toBe("Jean");
  });

  it("résultat vide → « Prono »", () => {
    expect(imageSafeName("🏀🔥")).toBe("Prono");
    expect(imageSafeName("李小龙")).toBe("Prono");
    expect(imageSafeName("   ")).toBe("Prono");
  });

  it("liste blanche : bornes vérifiées", () => {
    for (const c of [" ", "~", " ", "ÿ", "ı", "Œ", "œ", "–", "—", "‘", "’", "‚", "“", "”", "„", "•", "…", "€"]) {
      expect(isImageSafeChar(c), c).toBe(true);
    }
    for (const c of ["\u007F", "\u009F", "Ā", "ć", "ž", "Ő", "ș", "Ł", "​", "😀", "李"]) {
      expect(isImageSafeChar(c), c).toBe(false);
    }
  });
});
