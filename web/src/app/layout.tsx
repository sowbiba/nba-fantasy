import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import AppChrome, { AppMain } from "@/components/AppChrome";
import BottomNav from "@/components/BottomNav";
import HeaderControl from "@/components/HeaderControl";
import PullToRefresh from "@/components/PullToRefresh";
import ServiceWorker from "@/components/ServiceWorker";
import { getViewer } from "@/lib/viewer";

// Fonts self-hébergées (SIL OFL) : voir src/app/fonts/OFL-*.txt.
// Les fichiers *-400/500/600/700.woff (subset latin, hérités de next/font/google)
// viennent de Google Fonts ; leur cmap ne couvre que l'ASCII + Latin-1 (+ ı Œ œ
// et un peu de ponctuation), pas le latin étendu. Les fichiers *-latin-ext-*.woff
// viennent des paquets Fontsource (fontsource.org, mêmes polices Bebas Neue /
// Space Grotesk, licence SIL OFL identique — voir OFL-*.txt) et couvrent le
// latin étendu (ć č š ž đ ő ű ū ą ę ł ņ…), nécessaire pour les noms de joueurs
// accentués comme Jokić/Dončić/Nurkić/Valančiūnas/Šarić. Les deux jeux de
// fichiers sont téléchargés une fois puis embarqués pour que le build n'ait
// plus besoin du réseau.
//
// Chaque famille est déclarée via deux appels localFont : le subset latin
// (variable --font-*) et le subset latin-ext (variable --font-*-ext). Les
// deux variables sont empilées dans le font-family stack (globals.css) ; le
// navigateur bascule automatiquement glyphe par glyphe sur le subset
// latin-ext quand un caractère (ex. ć, č, š, ž, ū) manque au subset latin.
// `adjustFontFallback: false` sur les deux appels "latin" évite que leur
// @font-face de repli (métriques Arial/Times générées par next/font, insérée
// juste après la police elle-même dans le stack) ne s'intercale avant le
// subset ext — Arial a bien ces glyphes, mais on veut nos polices, pas Arial.
const display = localFont({
  src: "./fonts/bebas-neue-400.woff",
  weight: "400",
  display: "swap",
  variable: "--font-display",
  adjustFontFallback: false,
});

const displayExt = localFont({
  src: "./fonts/bebas-neue-latin-ext-400.woff",
  weight: "400",
  display: "swap",
  variable: "--font-display-ext",
});

const body = localFont({
  src: [
    { path: "./fonts/space-grotesk-400.woff", weight: "400" },
    { path: "./fonts/space-grotesk-500.woff", weight: "500" },
    { path: "./fonts/space-grotesk-600.woff", weight: "600" },
    { path: "./fonts/space-grotesk-700.woff", weight: "700" },
  ],
  display: "swap",
  variable: "--font-body",
  adjustFontFallback: false,
});

const bodyExt = localFont({
  src: [
    { path: "./fonts/space-grotesk-latin-ext-400.woff", weight: "400" },
    { path: "./fonts/space-grotesk-latin-ext-500.woff", weight: "500" },
    { path: "./fonts/space-grotesk-latin-ext-600.woff", weight: "600" },
    { path: "./fonts/space-grotesk-latin-ext-700.woff", weight: "700" },
  ],
  display: "swap",
  variable: "--font-body-ext",
});

export const metadata: Metadata = {
  title: "TTFL Advisor",
  description: "Outil d'aide à la décision pour la TrashTalk Fantasy League",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#050507",
  width: "device-width",
  initialScale: 1,
  // No maximumScale — blocking pinch-zoom is an a11y anti-pattern (WCAG 1.4.4)
  // and the default already prevents the iOS input-focus zoom jump.
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { owner } = await getViewer();
  return (
    <html
      lang="fr"
      className={`${display.variable} ${displayExt.variable} ${body.variable} ${bodyExt.variable}`}
    >
      <body className="font-body text-[color:var(--color-text)] min-h-screen">
        <ServiceWorker />
        <AppChrome>
          <PullToRefresh />
        </AppChrome>
        <AppMain>
          <AppChrome>
            <HeaderControl owner={owner} />
          </AppChrome>
          {children}
        </AppMain>
        <AppChrome>
          <BottomNav owner={owner} />
        </AppChrome>
      </body>
    </html>
  );
}
