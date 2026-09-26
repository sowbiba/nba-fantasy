"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { setX2 } from "@/app/actions";

export default function MyPickCard({
  date, playerId, playerName, team, isX2, x2Allowed,
}: {
  date: string; playerId: number; playerName: string; team: string; isX2: boolean; x2Allowed: boolean;
}) {
  const [x2, setLocalX2] = useState(isX2);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const toggle = () => {
    setError(null);
    startTransition(async () => {
      const res = await setX2({ date, value: !x2 });
      if (res.ok) setLocalX2(!x2);
      else setError(res.error);
    });
  };

  return (
    <div className="mx-3 mt-3 rounded-[var(--radius-card)] border border-[color:var(--color-emerald)]/40 bg-[color:var(--color-emerald)]/10 px-4 py-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-[color:var(--color-emerald)]">Ton pick de ce soir</div>
      <div className="flex items-center justify-between gap-3 mt-1">
        <Link href={`/player/${playerId}`} className="font-display text-2xl text-white tracking-wide truncate">
          {playerName} <span className="text-sm text-[color:var(--color-text-mute)]">{team}</span>
        </Link>
        {x2Allowed && (
          <button onClick={toggle} disabled={pending}
                  className={`shrink-0 px-3 py-1 rounded-full text-xs font-bold border ${x2
                    ? "bg-[color:var(--color-gold)] text-black border-[color:var(--color-gold)]"
                    : "border-white/15 text-[color:var(--color-text-soft)]"}`}>
            {pending ? "…" : x2 ? "x2 ACTIVÉ" : "ACTIVER x2"}
          </button>
        )}
      </div>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1">
        Tu peux le remplacer jusqu&apos;à la fermeture : choisis un autre joueur ci-dessous.
      </p>
      {error && <p role="alert" className="mt-1 text-xs text-[color:var(--color-crimson)]">{error}</p>}
    </div>
  );
}
