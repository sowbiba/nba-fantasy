"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Refresh button for PWA users. Invokes router.refresh() which re-runs
 * server components and refetches data. Also shows a spinner during refresh.
 *
 * Includes auto-refresh: re-queries every 60s when tab is visible.
 */
export default function RefreshButton() {
  const router = useRouter();
  const [spinning, setSpinning] = useState(false);

  const handleRefresh = () => {
    setSpinning(true);
    router.refresh();
    setTimeout(() => setSpinning(false), 800);
  };

  // Auto-refresh every 60 seconds when the page is visible
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (interval) return;
      interval = setInterval(() => {
        router.refresh();
      }, 60_000);
    };
    const stop = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        router.refresh();
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [router]);

  return (
    <button
      onClick={handleRefresh}
      aria-label="Rafraîchir"
      className="w-8 h-8 flex items-center justify-center rounded-full bg-gray-900 border border-gray-800 text-gray-400 hover:text-gray-100 hover:border-gray-700 transition-colors"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={spinning ? "animate-spin" : ""}
      >
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
        <path d="M3 3v5h5" />
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
        <path d="M16 16h5v5" />
      </svg>
    </button>
  );
}
