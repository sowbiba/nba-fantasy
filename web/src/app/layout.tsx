import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import HeaderControl from "@/components/HeaderControl";
import PullToRefresh from "@/components/PullToRefresh";
import ServiceWorker from "@/components/ServiceWorker";
import { getViewer } from "@/lib/viewer";

// Fonts self-hébergées (SIL OFL) : voir src/app/fonts/OFL-*.txt.
// Téléchargées depuis Google Fonts (fichiers non subsettés par next/font/google
// mais couvrant latin + latin-ext, nécessaires pour les noms de joueurs
// accentués comme Jokić/Dončić/Nurkić), embarquées pour que le build n'ait
// plus besoin du réseau.
const display = localFont({
  src: "./fonts/bebas-neue-400.woff",
  weight: "400",
  display: "swap",
  variable: "--font-display",
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
    <html lang="fr" className={`${display.variable} ${body.variable}`}>
      <body className="font-body text-[color:var(--color-text)] min-h-screen">
        <ServiceWorker />
        <PullToRefresh />
        <main
          className="max-w-lg mx-auto pb-24"
          style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
        >
          <HeaderControl owner={owner} />
          {children}
        </main>
        <BottomNav owner={owner} />
      </body>
    </html>
  );
}
