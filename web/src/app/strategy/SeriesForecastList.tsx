"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Series, SeriesForecast } from "@/types";

type Props = {
  series: Series[];
  forecasts: SeriesForecast[];
};

export default function SeriesForecastList({ series, forecasts }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const initial = new Map(forecasts.map((f) => [f.series_id, f]));
  const [state, setState] = useState(initial);
  const [savingId, setSavingId] = useState<number | null>(null);

  const upsert = async (
    seriesId: number,
    winner_team: string | null,
    expected_games: number | null
  ) => {
    setSavingId(seriesId);
    if (!winner_team || !expected_games) {
      const { error } = await supabase
        .from("series_forecast")
        .delete()
        .eq("series_id", seriesId);
      if (error) alert(`Erreur : ${error.message}`);
      else {
        const next = new Map(state);
        next.delete(seriesId);
        setState(next);
      }
    } else {
      const payload = {
        series_id: seriesId,
        winner_team,
        expected_games,
        updated_at: new Date().toISOString(),
      };
      const { error } = await supabase
        .from("series_forecast")
        .upsert(payload);
      if (error) alert(`Erreur : ${error.message}`);
      else {
        const next = new Map(state);
        next.set(seriesId, {
          ...payload,
          created_at:
            state.get(seriesId)?.created_at ?? new Date().toISOString(),
        } as SeriesForecast);
        setState(next);
      }
    }
    setSavingId(null);
    startTransition(() => router.refresh());
  };

  if (series.length === 0) {
    return (
      <p className="text-sm text-[color:var(--color-text-mute)]">
        Pas de séries actives.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {series.map((s) => {
        const current = state.get(s.id) ?? null;
        const played = s.home_wins + s.away_wins;
        const winner = current?.winner_team ?? "";
        const games = current?.expected_games ?? 0;
        const saving = savingId === s.id;

        return (
          <div
            key={s.id}
            className="rounded-[var(--radius-card-sm)] border border-white/[0.06] bg-[color:var(--color-surface)] px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-3 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-mono-num text-sm font-bold text-[color:var(--color-text)]">
                  {s.home_team}
                </span>
                <span className="text-[color:var(--color-text-mute)] text-xs">
                  {s.home_wins}-{s.away_wins}
                </span>
                <span className="font-mono-num text-sm font-bold text-[color:var(--color-text)]">
                  {s.away_team}
                </span>
              </div>
              <span className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)]">
                R{s.round} · {played} joué{played > 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select
                value={winner}
                disabled={saving || isPending}
                onChange={(e) =>
                  upsert(s.id, e.target.value || null, games || null)
                }
                className="bg-[color:var(--color-surface-2)] border border-white/10 text-[color:var(--color-text)] text-xs rounded px-2 py-1.5 disabled:opacity-50"
              >
                <option value="">Vainqueur…</option>
                <option value={s.home_team}>{s.home_team}</option>
                <option value={s.away_team}>{s.away_team}</option>
              </select>
              <select
                value={games || ""}
                disabled={saving || isPending}
                onChange={(e) =>
                  upsert(
                    s.id,
                    winner || null,
                    e.target.value ? parseInt(e.target.value, 10) : null
                  )
                }
                className="bg-[color:var(--color-surface-2)] border border-white/10 text-[color:var(--color-text)] text-xs rounded px-2 py-1.5 disabled:opacity-50"
              >
                <option value="">Nb matchs…</option>
                <option value="4">4-0</option>
                <option value="5">4-1</option>
                <option value="6">4-2</option>
                <option value="7">4-3</option>
              </select>
            </div>
          </div>
        );
      })}
      <p className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-1 leading-relaxed">
        Ton prono pèse 40% au départ, s&apos;efface linéairement après 4 matchs
        joués. Laisse vide pour ne rien influencer — l&apos;algo retombe sur le
        seeding.
      </p>
    </div>
  );
}
