"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { addSecondChance, cancelPick } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";
import { isClosed, pickPoints } from "@/lib/display";
import CorrectionPanel from "./CorrectionPanel";

export type HistoryRow = {
  id: number | null; date: string; player_id: number | null; player_name: string | null; team: string;
  actual_score: number | null; is_x2: boolean; second_chance: { bought_on: string; expires_on: string } | null;
};

export default function PicksHistory({ rows, today, todayClosingAt }: { rows: HistoryRow[]; today: string; todayClosingAt: string | null }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [correctingDate, setCorrectingDate] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const secondChance = (id: number) => {
    setMsg(null);
    startTransition(async () => {
      const res = await addSecondChance({ pickId: id });
      setMsg(res.ok ? "Seconde chance enregistrée : repick possible pendant 7 jours." : res.error);
    });
  };

  const cancel = (r: HistoryRow) => {
    if (confirmingId !== r.id) {
      setConfirmingId(r.id);
      return;
    }
    setMsg(null);
    startTransition(async () => {
      const res = await cancelPick({ date: r.date });
      setConfirmingId(null);
      if (!res.ok) setMsg(res.error);
    });
  };

  return (
    <div>
      <ol className="flex flex-col gap-1.5">
        {rows.map((r) => {
          const points = pickPoints(r.actual_score, r.is_x2);
          const closedToday = r.date === today && isClosed(todayClosingAt);
          const cancellable = r.id !== null && r.player_id !== null && r.date >= today && r.actual_score === null && !closedToday;
          // Correction (tâche 5) : uniquement les soirées déjà passées, avec ou sans pick.
          const correctable = r.date < today;
          return (
            <li key={r.id ?? r.date} className="flex flex-col gap-1 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  {r.player_id !== null ? (
                    <Link href={`/player/${r.player_id}`} className="text-sm font-semibold text-[color:var(--color-text)] truncate block">
                      {r.player_name} <span className="text-[11px] text-[color:var(--color-text-mute)]">{r.team}</span>
                    </Link>
                  ) : (
                    <div className="text-sm font-semibold text-[color:var(--color-text-mute)]">Aucun pick</div>
                  )}
                  <div className="text-[11px] text-[color:var(--color-text-mute)] capitalize">
                    {r.date > today ? `réservé · ${frLongDate(r.date)}` : frLongDate(r.date)}
                  </div>
                  <div className="mt-1 flex gap-3">
                    {cancellable && (
                      <button onClick={() => cancel(r)} disabled={pending}
                              className="text-[10px] underline text-[color:var(--color-text-soft)]">
                        {confirmingId === r.id ? "Confirmer (pas encore saisi sur TrashTalk)" : "Annuler"}
                      </button>
                    )}
                    {correctable && (
                      <button onClick={() => setCorrectingDate(correctingDate === r.date ? null : r.date)} disabled={pending}
                              className="text-[10px] underline text-[color:var(--color-text-soft)]">
                        {correctingDate === r.date ? "Fermer" : "Corriger"}
                      </button>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-display text-xl leading-none font-mono-num text-[color:var(--color-text)]">
                    {r.player_id === null ? "0" : points === null ? "—" : points}
                    {r.is_x2 && <span className="ml-1 text-xs text-[color:var(--color-gold)]">x2</span>}
                  </div>
                  {r.id !== null && r.actual_score === 0 && !r.second_chance && (
                    <button onClick={() => secondChance(r.id!)} disabled={pending}
                            className="mt-1 text-[10px] underline text-[color:var(--color-text-soft)]">
                      Seconde chance
                    </button>
                  )}
                  {r.second_chance && (
                    <div className="mt-1 text-[10px] text-[color:var(--color-emerald)]">
                      2de chance · jusqu&apos;au {frDayMonth(r.second_chance.expires_on)}
                    </div>
                  )}
                </div>
              </div>
              {correctingDate === r.date && (
                <CorrectionPanel date={r.date} currentPlayerId={r.player_id} onDone={() => setCorrectingDate(null)} />
              )}
            </li>
          );
        })}
      </ol>
      {msg && <p role="alert" className="text-xs text-[color:var(--color-text-soft)] mt-2">{msg}</p>}
    </div>
  );
}
