// Texte libre affiché dans l'image de partage (next/og / satori). Tout
// caractère absent des polices locales fait télécharger par satori une
// police ou un emoji de repli sur le réseau (jsdelivr / Google Fonts), sans
// délai d'expiration et sans option pour le désactiver : on réduit donc le
// nom à une liste blanche de glyphes réellement présents.
//
// Liste blanche = intersection des tables cmap de bebas-neue-400.woff,
// space-grotesk-400.woff et space-grotesk-700.woff (vérifiée en lisant les
// fichiers, 2026-09-30) : ASCII imprimable, Latin-1 (U+00A0-U+00FF), ı,
// Œ/œ et la ponctuation typographique courante. Le Latin étendu-A
// (ć, ž, ő, ș…) n'est PAS couvert : ces lettres sont ramenées à leur
// lettre de base (Jokić → Jokic) plutôt que supprimées.

const SAFE_RE = /^[ -~ -ÿıŒœ–—‘-‚“-„•…€]$/u;

// Lettres sans décomposition Unicode (NFD ne les ramène pas à une base).
const NO_DECOMPOSITION: Record<string, string> = { Ł: "L", ł: "l", Đ: "D", đ: "d", Ħ: "H", ħ: "h", Ŧ: "T", ŧ: "t" };

export function isImageSafeChar(ch: string): boolean {
  return SAFE_RE.test(ch);
}

export function imageSafeName(name: string, fallback = "Prono"): string {
  let out = "";
  for (const ch of name) {
    if (isImageSafeChar(ch)) {
      out += ch;
      continue;
    }
    const mapped = NO_DECOMPOSITION[ch];
    if (mapped) {
      out += mapped;
      continue;
    }
    // ć → c + accent combinant : on garde la base si elle est couverte.
    const base = ch.normalize("NFD").replace(/\p{M}/gu, "");
    if (base && base !== ch && [...base].every(isImageSafeChar)) out += base;
  }
  const cleaned = out.replace(/\s+/g, " ").trim();
  return cleaned || fallback;
}
