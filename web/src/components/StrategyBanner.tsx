import { Recommendation } from "@/types";

interface Props {
  recommendations: Recommendation[];
  gamesDaysRemaining: number;
}

export default function StrategyBanner({
  recommendations,
  gamesDaysRemaining,
}: Props) {
  const elites = recommendations.filter((r) => r.tier === "elite").length;
  const solids = recommendations.filter((r) => r.tier === "solid").length;
  const fillers = recommendations.filter((r) => r.tier === "filler").length;

  return (
    <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] px-4 py-3">
      <div className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-[color:var(--color-gold)] to-[color:var(--color-flame)]" />
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] tracking-[0.25em] uppercase font-bold text-[color:var(--color-gold)]">
              Capital
            </span>
            <span className="text-[10px] tracking-[0.2em] uppercase text-[color:var(--color-text-mute)]">
              / ~{gamesDaysRemaining}j restants
            </span>
          </div>
          <div className="flex items-baseline gap-3 mt-1 font-mono-num">
            <span className="flex items-baseline gap-1">
              <span className="font-display text-2xl text-[color:var(--color-gold)] leading-none">
                {elites}
              </span>
              <span className="text-[10px] tracking-[0.15em] uppercase text-[color:var(--color-gold)]/80">
                Elite
              </span>
            </span>
            <span className="w-px h-5 bg-white/10" />
            <span className="flex items-baseline gap-1">
              <span className="font-display text-2xl text-[color:var(--color-ice)] leading-none">
                {solids}
              </span>
              <span className="text-[10px] tracking-[0.15em] uppercase text-[color:var(--color-ice)]/80">
                Solide
              </span>
            </span>
            <span className="w-px h-5 bg-white/10" />
            <span className="flex items-baseline gap-1">
              <span className="font-display text-2xl text-[color:var(--color-text-soft)] leading-none">
                {fillers}
              </span>
              <span className="text-[10px] tracking-[0.15em] uppercase text-[color:var(--color-text-mute)]">
                Filler
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
