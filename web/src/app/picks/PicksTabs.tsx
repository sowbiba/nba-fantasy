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

function EstimatedVsActual({
  estimated,
  actual,
}: {
  estimated: number;
  actual: number;
}) {
  const diff = actual - estimated;
  const abs = Math.abs(diff);
  const color =
    diff > 3
      ? "text-[color:var(--color-emerald)]"
      : diff < -3
        ? "text-[color:var(--color-crimson)]"
        : "text-[color:var(--color-text-mute)]";
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  return (
    <div className="text-[9px] uppercase tracking-[0.12em] mt-0.5 font-mono-num flex items-center justify-end gap-1">
      <span className="text-[color:var(--color-text-dim)]">
        est. {estimated.toFixed(1)}
      </span>
      <span className={color}>
        {sign}
        {abs.toFixed(1)}
      </span>
    </div>
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

  // Engine accuracy over picks with both estimated_score (engine) and actual_score,
  // excluding x2 bonus picks where estimated_score is overloaded with the doubled
  // display value.
  const enginePicks = picks.filter(
    (p) =>
      !isX2(p) &&
      p.estimated_score !== null &&
      p.actual_score !== null
  );
  const errors = enginePicks.map(
    (p) => (p.actual_score as number) - (p.estimated_score as number)
  );
  const mae = errors.length
    ? errors.reduce((a, b) => a + Math.abs(b), 0) / errors.length
    : null;
  const bias = errors.length
    ? errors.reduce((a, b) => a + b, 0) / errors.length
    : null;

  if (scores.length === 0) return null;

  return (
    <>
      {/* mega total */}
      <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] p-5 mb-3">
        <div
          aria-hidden
          className="absolute -right-10 -top-10 w-56 h-56 rounded-full"
          style={{
            background:
              "radial-gradient(closest-side, rgba(255, 91, 31, 0.22), transparent 70%)",
          }}
        />
        <div className="relative flex items-end justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-[color:var(--color-text-mute)]">
              Total · {picks.length} pick{picks.length > 1 ? "s" : ""}
            </div>
            <div className="font-display text-6xl leading-none font-mono-num flame-text mt-2">
              {total}
            </div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mt-1">
              points
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
              Moyenne
            </div>
            <div className="font-display text-3xl leading-none font-mono-num text-white mt-1">
              {avg.toFixed(1)}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="rounded-[var(--radius-card-sm)] border border-[color:var(--color-emerald)]/20 bg-[color:var(--color-emerald)]/[0.05] p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-emerald)]">
            Meilleur
          </div>
          <div className="font-display text-3xl leading-none font-mono-num text-[color:var(--color-emerald)] mt-1">
            {best}
          </div>
        </div>
        <div className="rounded-[var(--radius-card-sm)] border border-[color:var(--color-crimson)]/20 bg-[color:var(--color-crimson)]/[0.05] p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-crimson)]">
            Pire
          </div>
          <div className="font-display text-3xl leading-none font-mono-num text-[color:var(--color-crimson)] mt-1">
            {worst}
          </div>
        </div>
      </div>

      {mae !== null && bias !== null && (
        <div className="rounded-[var(--radius-card-sm)] border border-[color:var(--color-ice)]/15 bg-[color:var(--color-ice)]/[0.04] p-3 mb-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-ice)]">
                Précision moteur · {enginePicks.length} pick
                {enginePicks.length > 1 ? "s" : ""}
              </div>
              <div className="text-[11px] text-[color:var(--color-text-mute)] mt-1">
                Écart absolu moyen : <span className="font-mono-num text-[color:var(--color-text)] font-semibold">{mae.toFixed(1)}</span> pts
              </div>
              <div className="text-[11px] text-[color:var(--color-text-mute)]">
                Biais moyen :{" "}
                <span
                  className={`font-mono-num font-semibold ${
                    bias > 2
                      ? "text-[color:var(--color-emerald)]"
                      : bias < -2
                        ? "text-[color:var(--color-crimson)]"
                        : "text-[color:var(--color-text)]"
                  }`}
                >
                  {bias > 0 ? "+" : ""}
                  {bias.toFixed(1)}
                </span>{" "}
                <span className="text-[color:var(--color-text-dim)]">
                  ({bias > 2 ? "réel > estimé" : bias < -2 ? "réel < estimé" : "neutre"})
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
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
      <div className="surface p-8 text-center">
        <div className="font-display text-2xl text-[color:var(--color-text-mute)]">
          Aucun pick
        </div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">
          pour cette période
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 stagger">
      {picks.map((pick) => {
        const player = playersMap[pick.player_id];
        const eff = effectiveScore(pick);
        const x2 = isX2(pick);
        const scored = pick.actual_score !== null;
        const scoreColor = !scored
          ? "text-[color:var(--color-text-mute)]"
          : eff >= 50
          ? "text-[color:var(--color-emerald)]"
          : eff >= 30
          ? "text-white"
          : "text-[color:var(--color-crimson)]";

        return (
          <div
            key={pick.id}
            className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/[0.04]"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-sm text-[color:var(--color-text)] truncate">
                  {player?.name || "?"}
                </span>
                {x2 && (
                  <span className="text-[9px] font-bold tracking-[0.15em] px-1.5 py-0.5 rounded bg-[color:var(--color-gold)] text-[color:var(--color-ink)]">
                    ×2
                  </span>
                )}
              </div>
              <div className="text-[11px] text-[color:var(--color-text-mute)] mt-0.5 font-mono-num">
                {new Date(pick.date + "T12:00:00").toLocaleDateString("fr-FR", {
                  day: "numeric",
                  month: "short",
                })}
                {player ? (
                  <span className="ml-1.5 text-[color:var(--color-text-soft)] font-semibold">
                    · {player.team}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div
                className={`font-display text-2xl leading-none font-mono-num ${scoreColor}`}
              >
                {scored ? eff : "—"}
              </div>
              {x2 ? (
                <div className="text-[9px] text-[color:var(--color-text-mute)] mt-0.5 font-mono-num">
                  {pick.actual_score} × 2
                </div>
              ) : (
                scored &&
                pick.estimated_score !== null && (
                  <EstimatedVsActual
                    estimated={pick.estimated_score}
                    actual={pick.actual_score as number}
                  />
                )
              )}
              {!scored && pick.estimated_score !== null && (
                <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-0.5 font-mono-num">
                  est. {pick.estimated_score.toFixed(1)}
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
    <div className="px-4 py-5 animate-fade-in">
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-flame)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-flame)]" />
          Historique
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          MES <span className="flame-text">PICKS</span>
        </h1>
      </div>

      {/* Tab switcher */}
      <div className="relative flex gap-1 p-1 rounded-[var(--radius-pill)] bg-[color:var(--color-surface)] border border-white/5 mb-5">
        <TabButton
          active={tab === "regular"}
          onClick={() => setTab("regular")}
          label="Saison régulière"
          total={regularTotal}
          accent="from-[color:var(--color-ice)]/25 to-[color:var(--color-ice)]/10"
        />
        <TabButton
          active={tab === "playoffs"}
          onClick={() => setTab("playoffs")}
          label="Playoffs"
          total={playoffTotal}
          accent="from-[color:var(--color-flame)]/30 to-[color:var(--color-gold)]/15"
        />
      </div>

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

function TabButton({
  active,
  onClick,
  label,
  total,
  accent,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  total: number;
  accent: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 relative px-3 py-2.5 rounded-[var(--radius-pill)] transition-all ${
        active
          ? `bg-gradient-to-br ${accent} text-white shadow-sm`
          : "text-[color:var(--color-text-mute)]"
      }`}
    >
      <span
        className={`block text-[10px] uppercase tracking-[0.18em] font-bold ${
          active ? "text-white" : ""
        }`}
      >
        {label}
      </span>
      <span
        className={`block font-display text-lg leading-none mt-0.5 font-mono-num ${
          active ? "text-white" : "text-[color:var(--color-text-soft)]"
        }`}
      >
        {total > 0 ? `${total} pts` : "—"}
      </span>
    </button>
  );
}
