"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

type Priority = 1 | 2 | 3 | null;

// Click cycles off → p3 (★) → p2 (★★) → p1 (★★★) → off.
const NEXT: Record<string, Priority> = {
  null: 3,
  "3": 2,
  "2": 1,
  "1": null,
};

export default function WatchlistStar({
  playerId,
  initialPriority,
}: {
  playerId: number;
  initialPriority: Priority;
}) {
  const router = useRouter();
  const [priority, setPriority] = useState<Priority>(initialPriority);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    const next = NEXT[String(priority)];
    setError(null);
    setPriority(next);

    if (next === null) {
      const { error } = await supabase
        .from("player_watchlist")
        .delete()
        .eq("player_id", playerId);
      if (error) {
        setPriority(priority);
        setError(error.message);
        return;
      }
    } else {
      const { error } = await supabase
        .from("player_watchlist")
        .upsert({ player_id: playerId, priority: next });
      if (error) {
        setPriority(priority);
        setError(error.message);
        return;
      }
    }
    startTransition(() => router.refresh());
  };

  const count = priority ?? 0;
  const filled = 4 - (priority ?? 4);
  const stars = "★★★".slice(0, filled);
  const empty = "☆☆☆".slice(0, 3 - filled);

  const label = priority
    ? `Must-play priorité ${priority}`
    : "Ajouter à ta watchlist";

  return (
    <button
      onClick={handleClick}
      disabled={isPending}
      aria-label={label}
      title={label}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-all disabled:opacity-50 ${
        count
          ? "border-[color:var(--color-gold)]/40 bg-[color:var(--color-gold)]/10 text-[color:var(--color-gold)]"
          : "border-white/10 bg-white/[0.02] text-[color:var(--color-text-mute)] hover:border-[color:var(--color-gold)]/30 hover:text-[color:var(--color-gold)]"
      }`}
    >
      <span className="font-mono-num text-[12px] tracking-widest leading-none">
        <span>{stars}</span>
        <span className="opacity-30">{empty}</span>
      </span>
      {error && (
        <span className="text-[9px] text-[color:var(--color-crimson)]">!</span>
      )}
    </button>
  );
}
