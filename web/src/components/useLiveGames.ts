"use client";

import { useEffect, useState } from "react";
import type { Game } from "@/types";
import { liveDates, mergeLive, needsLivePolling, type LiveGame, type LiveScore } from "@/lib/live";

const POLL_MS = 30_000;

/** Fusionne le live ESPN dans `games`, interrogé toutes les 30 s seulement
 *  tant qu'un match a commencé sans être final (sinon aucun appel). */
export function useLiveGames(games: Game[]): LiveGame[] {
  const [live, setLive] = useState<LiveScore[]>([]);
  const key = liveDates(games).join(",");

  useEffect(() => {
    if (!key) return;
    let stopped = false;
    const load = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const res = await fetch(`/api/live?dates=${key}`);
        if (res.ok && !stopped) setLive(await res.json());
      } catch {
        // réseau coupé : on garde le dernier état, prochain essai dans 30 s
      }
    };
    load();
    const id = setInterval(() => {
      if (needsLivePolling(games)) load();
    }, POLL_MS);
    const onVisible = () => document.visibilityState === "visible" && load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // `key` résume les matchs à suivre ; `games` change à chaque rendu serveur.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return live.length ? mergeLive(games, live) : games;
}
