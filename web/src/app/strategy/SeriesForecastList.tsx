"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Series, SeriesForecast } from "@/types";

type Props = {
  series: Series[];
  forecasts: SeriesForecast[];
};

type Draft = { winner_team: string; expected_games: number };

export default function SeriesForecastList({ series, forecasts }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const initial = new Map(forecasts.map((f) => [f.series_id, f]));
  const [state, setState] = useState(initial);
  // Draft = the in-progress selections shown in the dropdowns. We only
  // commit to the DB once BOTH winner and expected_games are filled,
  // because the schema requires both NOT NULL — saving piecemeal is what
  // caused the previous "rien n'est save" bug (changing one select
  // routed to the delete branch because the other was still null).
  const [drafts, setDrafts] = useState<Map<number, Draft>>(new Map());
  const [savingId, setSavingId] = useState<number | null>(null);

  const persistFull = async (
    seriesId: number,
    winner_team: string,
    expected_games: number
  ) => {
    setSavingId(seriesId);
    const payload = {
      series_id: seriesId,
      winner_team,
      expected_games,
      updated_at: new Date().toISOString(),
    };
    const { error } = await supabase.from("series_forecast").upsert(payload);
    setSavingId(null);
    if (error) {
      alert(`Erreur : ${error.message}`);
      return;
    }
    setState((prev) => {
      const next = new Map(prev);
      next.set(seriesId, {
        ...payload,
        created_at: prev.get(seriesId)?.created_at ?? new Date().toISOString(),
      } as SeriesForecast);
      return next;
    });
    setDrafts((prev) => {
      const next = new Map(prev);
      next.delete(seriesId);
      return next;
    });
    startTransition(() => router.refresh());
  };

  const clearForecast = async (seriesId: number) => {
    setSavingId(seriesId);
    const { error } = await supabase
      .from("series_forecast")
      .delete()
      .eq("series_id", seriesId);
    setSavingId(null);
    if (error) {
      alert(`Erreur : ${error.message}`);
      return;
    }
    setState((prev) => {
      const next = new Map(prev);
      next.delete(seriesId);
      return next;
    });
    setDrafts((prev) => {
      const next = new Map(prev);
      next.delete(seriesId);
      return next;
    });
    startTransition(() => router.refresh());
  };

  const onChange = (
    seriesId: number,
    field: "winner_team" | "expected_games",
    rawValue: string
  ) => {
    const persisted = state.get(seriesId);
    const draft = drafts.get(seriesId);
    const baseWinner = draft?.winner_team ?? persisted?.winner_team ?? "";
    const baseGames = draft?.expected_games ?? persisted?.expected_games ?? 0;

    const winner = field === "winner_team" ? rawValue : baseWinner;
    const games =
      field === "expected_games"
        ? rawValue
          ? parseInt(rawValue, 10)
          : 0
        : baseGames;

    // Empty selection on either field with a persisted forecast → wipe it.
    if ((!winner || !games) && persisted) {
      clearForecast(seriesId);
      return;
    }

    if (winner && games) {
      // Both set → commit immediately.
      persistFull(seriesId, winner, games);
      return;
    }

    // Only one set so far → keep it locally until the other arrives.
    setDrafts((prev) => {
      const next = new Map(prev);
      next.set(seriesId, { winner_team: winner, expected_games: games });
      return next;
    });
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
        const persisted = state.get(s.id);
        const draft = drafts.get(s.id);
        const winner = draft?.winner_team ?? persisted?.winner_team ?? "";
        const games = draft?.expected_games ?? persisted?.expected_games ?? 0;
        const played = s.home_wins + s.away_wins;
        const saving = savingId === s.id;
        const partial = !!draft && (!winner || !games);

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
                {partial && (
                  <span className="ml-1.5 text-[color:var(--color-flame)]">
                    · brouillon
                  </span>
                )}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select
                value={winner}
                disabled={saving || isPending}
                onChange={(e) => onChange(s.id, "winner_team", e.target.value)}
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
                  onChange(s.id, "expected_games", e.target.value)
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
