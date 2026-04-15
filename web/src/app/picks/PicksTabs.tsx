"use client";

import { useState } from "react";
import { Pick, Player } from "@/types";

function effectiveScore(pick: Pick): number {
  if (
    pick.estimated_score !== null &&
    pick.actual_score !== null &&
    pick.estimated_score !== pick.actual_score &&
    pick.estimated_score === pick.actual_score * 2
  ) {
    return pick.estimated_score;
  }
  return pick.actual_score ?? 0;
}

function isX2(pick: Pick): boolean {
  return (
    pick.estimated_score !== null &&
    pick.actual_score !== null &&
    pick.estimated_score === pick.actual_score * 2
  );
}

function StatsGrid({ picks }: { picks: Pick[] }) {
  const scores = picks
    .filter((p) => p.actual_score !== null)
    .map((p) => effectiveScore(p));
  const total = scores.reduce((a, b) => a + b, 0);
  const avg = scores.length ? total / scores.length : 0;
  const best = scores.length ? Math.max(...scores) : 0;
  const worst = scores.length ? Math.min(...scores) : 0;

  if (scores.length === 0) return null;

  return (
    <>
      <p className="text-gray-500 text-sm mb-3">
        {picks.length} pick{picks.length > 1 ? "s" : ""} · Total :{" "}
        <span className="text-gray-100 font-bold">{total} pts</span>
      </p>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">{avg.toFixed(1)}</div>
          <div className="text-gray-500 text-[0.65em]">Avg / pick</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold text-green-500">{best}</div>
          <div className="text-gray-500 text-[0.65em]">Meilleur</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold text-red-400">{worst}</div>
          <div className="text-gray-500 text-[0.65em]">Pire</div>
        </div>
      </div>
    </>
  );
}

function PickList({
  picks,
  playersMap,
}: {
  picks: Pick[];
  playersMap: Record<number, Player>;
}) {
  if (picks.length === 0) {
    return (
      <p className="text-gray-600 text-sm text-center py-8">
        Aucun pick pour cette période.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {picks.map((pick) => {
        const player = playersMap[pick.player_id];
        const eff = effectiveScore(pick);
        const x2 = isX2(pick);
        const scoreColor =
          pick.actual_score === null
            ? "text-gray-500"
            : eff >= 50
              ? "text-green-500"
              : eff >= 30
                ? "text-gray-100"
                : "text-red-400";
        return (
          <div
            key={pick.id}
            className="bg-gray-900 rounded-lg px-3 py-2.5 flex justify-between items-center"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-gray-100">
                  {player?.name || "?"}
                </span>
                {x2 && (
                  <span className="bg-amber-500 text-gray-950 text-[0.6em] px-1.5 py-0.5 rounded font-bold">
                    x2
                  </span>
                )}
              </div>
              <div className="text-gray-500 text-xs">
                {new Date(pick.date + "T12:00:00").toLocaleDateString("fr-FR", {
                  day: "numeric",
                  month: "short",
                })}
                {player ? ` · ${player.team}` : ""}
              </div>
            </div>
            <div className="text-right">
              <div className={`font-bold ${scoreColor}`}>
                {pick.actual_score !== null ? eff : "—"}
              </div>
              {x2 && (
                <div className="text-gray-600 text-[0.6em]">
                  ({pick.actual_score} × 2)
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function PicksTabs({
  picks,
  playersMap,
}: {
  picks: Pick[];
  playersMap: Record<number, Player>;
}) {
  const [tab, setTab] = useState<"regular" | "playoffs">("regular");

  const regularPicks = picks.filter((p) => p.mode === "regular");
  const playoffPicks = picks.filter((p) => p.mode === "playoffs");

  const regularTotal = regularPicks
    .filter((p) => p.actual_score !== null)
    .reduce((a, p) => a + effectiveScore(p), 0);
  const playoffTotal = playoffPicks
    .filter((p) => p.actual_score !== null)
    .reduce((a, p) => a + effectiveScore(p), 0);

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-3">Mes picks</h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setTab("regular")}
          className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors ${
            tab === "regular"
              ? "bg-blue-600 text-white"
              : "bg-gray-900 text-gray-500"
          }`}
        >
          Saison régulière
          <span className="block text-xs font-normal mt-0.5 opacity-75">
            {regularTotal} pts
          </span>
        </button>
        <button
          onClick={() => setTab("playoffs")}
          className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors ${
            tab === "playoffs"
              ? "bg-amber-600 text-white"
              : "bg-gray-900 text-gray-500"
          }`}
        >
          Playoffs
          <span className="block text-xs font-normal mt-0.5 opacity-75">
            {playoffTotal > 0 ? `${playoffTotal} pts` : "—"}
          </span>
        </button>
      </div>

      {/* Content */}
      {tab === "regular" && (
        <>
          <StatsGrid picks={regularPicks} />
          <PickList picks={regularPicks} playersMap={playersMap} />
        </>
      )}
      {tab === "playoffs" && (
        <>
          <StatsGrid picks={playoffPicks} />
          <PickList picks={playoffPicks} playersMap={playersMap} />
        </>
      )}
    </div>
  );
}
