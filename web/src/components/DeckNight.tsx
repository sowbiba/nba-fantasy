"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { savePick } from "@/app/actions";
import { frLongDate, parisTime } from "@/lib/date";
import { HARD_OUT_STATUSES, isClosed } from "@/lib/display";

export type DeckNightProps = {
  date: string; closingAt: string; nGames: number; isPhantom: boolean; isToday: boolean;
  pick: { playerId: number; name: string; team: string; injury: string | null; isX2: boolean } | null;
  suggestion: { playerId: number; name: string; team: string; gameId: string; projection: number; explanation: string; isX2: boolean } | null;
};

export default function DeckNight(p: DeckNightProps) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const closed = isClosed(p.closingAt);

  const reserve = () => {
    if (!p.suggestion) return;
    const s = p.suggestion;
    setMsg(null);
    startTransition(async () => {
      const res = await savePick({ date: p.date, playerId: s.playerId, gameId: s.gameId });
      setMsg(res.ok ? "Réservé. Pense à le reporter sur trashtalk.co." : res.error);
    });
  };

  return (
    <div className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-3 py-2.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-[color:var(--color-text)] capitalize">
          {p.isToday ? "Ce soir" : frLongDate(p.date)}
        </span>
        <span className="text-[10px] text-[color:var(--color-text-mute)]">
          {p.nGames} match{p.nGames > 1 ? "s" : ""} · fermeture {parisTime(p.closingAt)}
        </span>
      </div>
      {p.isPhantom && (
        <p className="mt-1 text-xs text-[color:var(--color-crimson)]">Soirée fantôme : aucun match réel, déplace ta réservation.</p>
      )}
      {p.pick ? (
        <div className="mt-1 text-sm">
          <Link href={`/player/${p.pick.playerId}`} className="font-semibold text-[color:var(--color-emerald)]">
            {p.pick.name}
          </Link>{" "}
          <span className="text-[11px] text-[color:var(--color-text-mute)]">
            {p.pick.team}{p.pick.isX2 ? " · x2" : ""}
            {p.suggestion?.isX2 && !p.pick.isX2 ? " · plan : x2 ce soir-là" : ""}
          </span>
          {p.pick.injury && HARD_OUT_STATUSES.has(p.pick.injury) && !closed && (
            <p className="text-xs text-[color:var(--color-crimson)]">⚠️ {p.pick.injury} : remplace-le avant la fermeture.</p>
          )}
        </div>
      ) : p.suggestion ? (
        <div className="mt-1 flex items-center justify-between gap-3">
          <div className="min-w-0 text-sm">
            <Link href={`/player/${p.suggestion.playerId}`} className="text-[color:var(--color-text)]">
              {p.suggestion.name}
            </Link>{" "}
            {p.suggestion.isX2 && (
              <span title="Le plan suggère le x2 cette nuit-là" className="rounded-full bg-[color:var(--color-gold)]/15 border border-[color:var(--color-gold)]/40 px-1.5 py-0.5 text-[10px] font-bold text-[color:var(--color-gold)]">
                x2
              </span>
            )}{" "}
            <span className="text-[11px] text-[color:var(--color-text-mute)]">{p.suggestion.explanation}</span>
          </div>
          {closed ? (
            <span className="shrink-0 text-[11px] text-[color:var(--color-text-mute)]">Fermé</span>
          ) : (
            <button onClick={reserve} disabled={pending}
                    className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
              RÉSERVER
            </button>
          )}
        </div>
      ) : (
        <p className="mt-1 text-xs text-[color:var(--color-text-mute)]">Pas encore de suggestion.</p>
      )}
      {msg && <p role="alert" className="mt-1 text-xs text-[color:var(--color-text-soft)]">{msg}</p>}
    </div>
  );
}
