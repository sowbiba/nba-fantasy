"use client";

import { useSyncExternalStore } from "react";
import { SyncLog } from "@/types";
import { todayParis } from "@/lib/date";

/**
 * External store that emits the current minute as an epoch-minute bucket.
 * The server snapshot is 0 so that rendering is stable until hydration.
 */
function subscribe(cb: () => void) {
  const id = setInterval(cb, 60_000);
  return () => clearInterval(id);
}
function getSnapshot() {
  return Math.floor(Date.now() / 60_000);
}
function getServerSnapshot() {
  return 0;
}

export default function SyncStatus({ sync }: { sync: SyncLog | null }) {
  const minuteBucket = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot
  );

  if (!sync) return null;

  const finishedAt = sync.finished_at ? new Date(sync.finished_at) : null;
  // minuteBucket is 0 on SSR, real minute index on client.
  const nowMs = minuteBucket * 60_000;
  const isStale =
    finishedAt && minuteBucket > 0
      ? nowMs - finishedAt.getTime() > 12 * 60 * 60 * 1000
      : false;
  const isError = sync.status === "error";

  const timeStr = finishedAt
    ? finishedAt.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "...";
  const dateStr = finishedAt
    ? finishedAt.toLocaleDateString("fr-FR", {
        day: "numeric",
        month: "short",
      })
    : "";

  // Compare calendar days explicitly in Paris tz (not the runtime's tz) so
  // SSR and client agree and "aujourd'hui" is correct for the user.
  const finishedDayParis = sync.finished_at
    ? new Date(sync.finished_at).toLocaleDateString("en-CA", {
        timeZone: "Europe/Paris",
      })
    : null;
  const isToday = finishedDayParis === todayParis();

  const dotColor = isError
    ? "bg-[color:var(--color-crimson)]"
    : isStale
    ? "bg-amber-400"
    : "bg-[color:var(--color-emerald)]";

  const ringColor = isError
    ? "after:bg-[color:var(--color-crimson)]/30"
    : isStale
    ? "after:bg-amber-400/30"
    : "after:bg-[color:var(--color-emerald)]/30";

  return (
    <div className="flex items-center gap-2 px-4 py-1.5">
      <span className="relative flex items-center justify-center">
        <span className={`relative w-1.5 h-1.5 rounded-full ${dotColor}`} />
        <span
          className={`absolute w-3 h-3 rounded-full after:content-[''] after:absolute after:inset-0 after:rounded-full ${ringColor} after:animate-ping`}
          aria-hidden
        />
      </span>
      <span className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
        {isError ? "Erreur sync" : "Sync"} ·{" "}
        <span className="text-[color:var(--color-text-soft)] font-mono-num tracking-normal normal-case">
          {isToday ? `aujourd'hui, ${timeStr}` : `${dateStr}, ${timeStr}`}
        </span>
      </span>
    </div>
  );
}
