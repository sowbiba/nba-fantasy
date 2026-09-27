import type { Metadata, Viewport } from "next";
import { Bebas_Neue, Space_Grotesk } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import PullToRefresh from "@/components/PullToRefresh";
import ServiceWorker from "@/components/ServiceWorker";
import SignOutButton from "@/components/SignOutButton";
import { getViewer } from "@/lib/viewer";

const display = Bebas_Neue({
  weight: "400",
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
});

const body = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
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
        <div
          className="fixed inset-x-0 top-0 z-40 pointer-events-none"
          style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
        >
          <div className="max-w-lg mx-auto flex justify-end">
            <div className="pointer-events-auto px-4 py-2">
              {owner ? (
                <SignOutButton />
              ) : (
                <Link
                  href="/connexion"
                  className="text-[11px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)] underline"
                >
                  Mode connecté
                </Link>
              )}
            </div>
          </div>
        </div>
        <main className="max-w-lg mx-auto pb-24">{children}</main>
        <BottomNav owner={owner} />
      </body>
    </html>
  );
}
