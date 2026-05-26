import type { Metadata, Viewport } from "next";
import { Bebas_Neue, Space_Grotesk } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import PullToRefresh from "@/components/PullToRefresh";

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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className={`${display.variable} ${body.variable}`}>
      <body className="font-body text-[color:var(--color-text)] min-h-screen">
        <PullToRefresh />
        <main className="max-w-lg mx-auto pb-24">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
