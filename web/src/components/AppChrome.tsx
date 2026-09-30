"use client";

import { usePathname } from "next/navigation";
import { isStandalonePath } from "@/lib/standalone";

/** Habillage de l'application (en-tête, navigation, tirer-pour-rafraîchir) :
 *  masqué sur les pages autonomes (voir STANDALONE_PREFIXES). */
export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (isStandalonePath(pathname)) return null;
  return <>{children}</>;
}

/** `<main>` de l'application : la marge basse réservée à la BottomNav
 *  n'a pas lieu d'être sur les pages autonomes (pas de BottomNav). */
export function AppMain({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <main
      className={isStandalonePath(pathname) ? "max-w-lg mx-auto" : "max-w-lg mx-auto pb-24"}
      style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
    >
      {children}
    </main>
  );
}
