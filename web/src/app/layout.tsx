import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import PullToRefresh from "@/components/PullToRefresh";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TTFL Advisor",
  description: "Outil d'aide à la décision pour la TrashTalk Fantasy League",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen`}>
        <PullToRefresh />
        <main className="max-w-lg mx-auto pb-20">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
