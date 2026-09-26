"use client";

import { useState, useTransition } from "react";
import { savePick } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";

export type CalendarNight = {
  night: string; game_id: string; opponent: string; is_home: boolean;
  ok: boolean; available_from: string | null; reason: string | null; closing_at: string;
};

const REASON: Record<string, string> = {
  reserved_nearby: "réservé à moins de 30 jours",
  playoffs_used: "déjà utilisé en playoffs",
  team_eliminated: "équipe éliminée",
  not_qualified: "équipe non qualifiée",
};

export default function PickControls({
  playerId, nights, today, lastBookable,
}: { playerId: number; nights: CalendarNight[]; today: string; lastBookable: string }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, startTransition] = useTransition();

  const book = (n: CalendarNight) => {
    setMsg(null);
    startTransition(async () => {
      const res = await savePick({ date: n.night, playerId, gameId: n.game_id });
      setMsg(res.ok
        ? { ok: true, text: n.night === today ? "Pické pour ce soir." : `Réservé pour le ${frDayMonth(n.night)}.` }
        : { ok: false, text: res.error });
    });
  };

  if (nights.length === 0) {
    return <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL pour son équipe dans les 30 prochains jours.</p>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {nights.map((n) => {
        const bookable = n.ok && n.night <= lastBookable;
        const status = n.ok
          ? "disponible"
          : n.reason === "cooldown" && n.available_from
            ? `dispo le ${frDayMonth(n.available_from)}`
            : REASON[n.reason ?? ""] ?? "indisponible";
        return (
          <div key={n.night} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
            <div className="min-w-0">
              <div className="text-sm text-[color:var(--color-text)] capitalize">
                {n.night === today ? "Ce soir" : frLongDate(n.night)} · {n.is_home ? "vs" : "@"} {n.opponent}
              </div>
              <div className={`text-[11px] ${n.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text-mute)]"}`}>{status}</div>
            </div>
            {bookable && (
              <button onClick={() => book(n)} disabled={pending}
                      className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
                {n.night === today ? "PICKER" : "RÉSERVER"}
              </button>
            )}
          </div>
        );
      })}
      {msg && <p role="alert" className={`mt-1 text-xs ${msg.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-crimson)]"}`}>{msg.text}</p>}
    </div>
  );
}
