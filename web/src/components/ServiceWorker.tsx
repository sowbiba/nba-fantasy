"use client";

import { useEffect } from "react";

/** Enregistre le service worker écrit à la main (tâche 7 : push web,
 *  pas de cache hors-ligne). Monté une fois dans layout.tsx. */
export default function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch((e) => {
      console.error("Échec de l'enregistrement du service worker :", e);
    });
  }, []);
  return null;
}
