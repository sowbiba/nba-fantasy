"use client";

import { useState, useTransition } from "react";
import { savePick } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";
import { HARD_OUT_STATUSES, isClosed } from "@/lib/display";

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
  playerId, nights, today, lastBookable, picksByDate, injuryStatus,
}: {
  playerId: number; nights: CalendarNight[]; today: string; lastBookable: string;
  injuryStatus: string | null;
  picksByDate: Record<string, { playerId: number; name: string }>;
}) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmingNight, setConfirmingNight] = useState<string | null>(null);
  const [pendingNight, setPendingNight] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const book = (n: CalendarNight) => {
    setMsg(null);
    setConfirmingNight(null);
    setPendingNight(n.night);
    startTransition(async () => {
      try {
        const res = await savePick({ date: n.night, playerId, gameId: n.game_id });
        setMsg(res.ok
          ? { ok: true, text: n.night === today ? "Pické pour ce soir." : `Réservé pour le ${frDayMonth(n.night)}.` }
          : { ok: false, text: res.error });
      } catch (e) {
        setMsg({ ok: false, text: e instanceof Error ? e.message : "Échec de la réservation." });
      } finally {
        setPendingNight(null);
      }
    });
  };

  const onBookableClick = (n: CalendarNight, other: { playerId: number; name: string } | undefined) => {
    if (other && confirmingNight !== n.night) {
      setConfirmingNight(n.night);
      return;
    }
    book(n);
  };

  if (nights.length === 0) {
    return <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL pour son équipe dans les 30 prochains jours.</p>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {nights.map((n) => {
        const existing = picksByDate[n.night];
        const isOwnPick = existing?.playerId === playerId;
        const closed = isClosed(n.closing_at);
        const canReplace = !closed && !!existing && !isOwnPick && n.night <= lastBookable;
        // Sans pick existant, n.ok vient du calendrier. Avec pick existant (le
        // sien), n.ok peut être false à cause du cooldown que ce pick crée
        // lui-même : dans ce cas c'est « Ton pick », pas indisponible.
        const bookable = !isOwnPick && !existing && !closed && n.ok && n.night <= lastBookable;
        // « disponible » = autorisé par les règles (cooldown, R3/R4/R5) ; la
        // blessure est un autre sujet, affichée à part pour ne pas tromper.
        const injured = !!injuryStatus && HARD_OUT_STATUSES.has(injuryStatus);
        const status = isOwnPick
          ? "ton pick"
          : n.ok
            ? injured ? `pickable, mais blessé (${injuryStatus})` : "disponible"
            : n.reason === "cooldown" && n.available_from
              ? `dispo le ${frDayMonth(n.available_from)}`
              : REASON[n.reason ?? ""] ?? "indisponible";
        return (
          <div key={n.night} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
            <div className="min-w-0">
              <div className="text-sm text-[color:var(--color-text)] capitalize">
                {n.night === today ? "Ce soir" : frLongDate(n.night)} · {n.is_home ? "vs" : "@"} {n.opponent}
              </div>
              <div className={`text-[11px] ${n.ok && !isOwnPick && injured ? "text-[color:var(--color-crimson)]" : isOwnPick || n.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text-mute)]"}`}>{status}</div>
            </div>
            {(bookable || canReplace) && (
              <button onClick={() => onBookableClick(n, canReplace ? existing : undefined)} disabled={pendingNight === n.night}
                      className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
                {canReplace
                  ? (confirmingNight === n.night ? "Confirmer" : `Remplacer ${existing!.name}`)
                  : n.night === today ? "PICKER" : "RÉSERVER"}
              </button>
            )}
          </div>
        );
      })}
      {msg && <p role="alert" className={`mt-1 text-xs ${msg.ok ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-crimson)]"}`}>{msg.text}</p>}
    </div>
  );
}
