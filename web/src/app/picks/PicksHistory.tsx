"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { addSecondChance } from "@/app/actions";
import { frDayMonth, frLongDate } from "@/lib/date";

export type HistoryRow = {
  id: number; date: string; player_id: number; player_name: string; team: string;
  actual_score: number | null; is_x2: boolean; has_second_chance: boolean;
};

export default function PicksHistory({ rows, today }: { rows: HistoryRow[]; today: string }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const secondChance = (id: number) => {
    setMsg(null);
    startTransition(async () => {
      const res = await addSecondChance({ pickId: id, boughtOn: today });
      setMsg(res.ok ? "Seconde chance enregistrée : repick possible pendant 7 jours." : res.error);
    });
  };

  return (
    <div>
      <ol className="flex flex-col gap-1.5">
        {rows.map((r) => {
          const points = r.actual_score === null ? null : r.actual_score * (r.is_x2 ? 2 : 1);
          return (
            <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
              <div className="min-w-0">
                <Link href={`/player/${r.player_id}`} className="text-sm font-semibold text-[color:var(--color-text)] truncate block">
                  {r.player_name} <span className="text-[11px] text-[color:var(--color-text-mute)]">{r.team}</span>
                </Link>
                <div className="text-[11px] text-[color:var(--color-text-mute)] capitalize">
                  {r.date > today ? `réservé · ${frLongDate(r.date)}` : frLongDate(r.date)}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="font-display text-xl leading-none font-mono-num text-[color:var(--color-text)]">
                  {points === null ? "—" : points}
                  {r.is_x2 && <span className="ml-1 text-xs text-[color:var(--color-gold)]">x2</span>}
                </div>
                {r.actual_score === 0 && !r.has_second_chance && (
                  <button onClick={() => secondChance(r.id)} disabled={pending}
                          className="mt-1 text-[10px] underline text-[color:var(--color-text-soft)]">
                    Seconde chance
                  </button>
                )}
                {r.has_second_chance && <div className="mt-1 text-[10px] text-[color:var(--color-emerald)]">2de chance · {frDayMonth(r.date)}</div>}
              </div>
            </li>
          );
        })}
      </ol>
      {msg && <p role="alert" className="text-xs text-[color:var(--color-text-soft)] mt-2">{msg}</p>}
    </div>
  );
}
