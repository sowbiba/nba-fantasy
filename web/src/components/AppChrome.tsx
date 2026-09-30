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
