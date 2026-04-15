"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Native-feeling pull-to-refresh for the PWA. Only triggers when the user
 * is at scrollTop = 0 and pulls down enough.
 */
export default function PullToRefresh() {
  const router = useRouter();
  const [pullDistance, setPullDistance] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startYRef = useRef<number | null>(null);
  const activeRef = useRef(false);

  useEffect(() => {
    const THRESHOLD = 80;
    const MAX_PULL = 140;

    const onTouchStart = (e: TouchEvent) => {
      if (window.scrollY > 0) return;
      startYRef.current = e.touches[0].clientY;
      activeRef.current = true;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!activeRef.current || startYRef.current === null) return;
      const dy = e.touches[0].clientY - startYRef.current;
      if (dy <= 0) {
        setPullDistance(0);
        return;
      }
      if (window.scrollY > 0) {
        activeRef.current = false;
        setPullDistance(0);
        return;
      }
      const distance = Math.min(dy, MAX_PULL);
      setPullDistance(distance);
    };

    const onTouchEnd = () => {
      if (!activeRef.current) return;
      activeRef.current = false;
      if (pullDistance >= THRESHOLD) {
        setRefreshing(true);
        setPullDistance(60);
        router.refresh();
        setTimeout(() => {
          setRefreshing(false);
          setPullDistance(0);
        }, 900);
      } else {
        setPullDistance(0);
      }
      startYRef.current = null;
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [pullDistance, router]);

  if (pullDistance === 0 && !refreshing) return null;

  const progress = Math.min(pullDistance / 80, 1);
  const opacity = Math.min(pullDistance / 40, 1);

  return (
    <div
      style={{
        height: `${pullDistance}px`,
        opacity,
      }}
      className="fixed top-0 left-0 right-0 z-40 flex items-end justify-center pb-2 pointer-events-none"
    >
      <div className="flex items-center gap-2 backdrop-blur-xl bg-[color:var(--color-ink)]/80 rounded-full px-4 py-2 border border-[color:var(--color-flame)]/30 shadow-[0_4px_20px_rgba(255,91,31,0.25)]">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-[color:var(--color-flame)] ${
            refreshing ? "animate-spin" : ""
          }`}
          style={{
            transform: refreshing ? "" : `rotate(${progress * 360}deg)`,
            transition: refreshing ? "" : "transform 50ms linear",
          }}
        >
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <path d="M3 3v5h5" />
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
          <path d="M16 16h5v5" />
        </svg>
        <span className="text-[10px] uppercase tracking-[0.2em] font-semibold text-[color:var(--color-text-soft)]">
          {refreshing
            ? "Synchro…"
            : progress >= 1
            ? "Relâche"
            : "Tire"}
        </span>
      </div>
    </div>
  );
}
