"use client";

import { SyncLog } from "@/types";

export default function SyncStatus({ sync }: { sync: SyncLog | null }) {
  if (!sync) return null;

  const finishedAt = sync.finished_at ? new Date(sync.finished_at) : null;
  const isStale = finishedAt
    ? Date.now() - finishedAt.getTime() > 12 * 60 * 60 * 1000
    : true;
  const isError = sync.status === "error";

  const timeStr = finishedAt
    ? finishedAt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : "...";
  const dateStr = finishedAt
    ? finishedAt.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })
    : "";

  const isToday = finishedAt?.toDateString() === new Date().toDateString();

  return (
    <div className="flex items-center gap-1.5 px-4 py-1">
      <div
        className={`w-1.5 h-1.5 rounded-full ${
          isError ? "bg-red-500" : isStale ? "bg-orange-400" : "bg-green-500"
        }`}
      />
      <span className="text-xs text-gray-500">
        Dernière synchro : {isToday ? `aujourd'hui à ${timeStr}` : `${dateStr} à ${timeStr}`}
      </span>
    </div>
  );
}
