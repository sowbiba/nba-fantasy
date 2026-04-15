import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

/**
 * Surfaces the top opportunities where a player benefits from a teammate being OUT.
 * These are picks the engine has already identified via the "teammate_out" tag.
 */
export default function InjuryArbitrage({
  recs,
}: {
  recs: RecommendationWithPlayer[];
}) {
  const opportunities = recs
    .filter((r) => r.tags.includes("teammate_out"))
    .slice(0, 3);

  if (opportunities.length === 0) return null;

  return (
    <section className="mt-4 px-3">
      <div className="flex items-end justify-between mb-2 px-1">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-violet)]">
            <span className="w-1 h-1 rounded-full bg-[color:var(--color-violet)] animate-live-dot" />
            Usage+
          </span>
        </div>
        <span className="text-[10px] tracking-[0.2em] uppercase text-[color:var(--color-text-mute)]">
          Coéquipier out
        </span>
      </div>

      <div className="relative overflow-hidden rounded-[var(--radius-card)] border border-[color:var(--color-violet)]/20 bg-gradient-to-br from-[color:var(--color-violet)]/[0.06] to-[color:var(--color-surface)] p-3">
        <div
          aria-hidden
          className="absolute -right-10 -bottom-10 w-40 h-40 pointer-events-none"
          style={{
            background:
              "radial-gradient(closest-side, rgba(167, 139, 250, 0.15), transparent 70%)",
          }}
        />

        <h3 className="font-display text-xl tracking-wide text-white leading-tight mb-2 relative">
          Opportunités <span className="text-[color:var(--color-violet)]">blessures</span>
        </h3>
        <p className="text-[11px] text-[color:var(--color-text-mute)] mb-3 leading-snug relative">
          Un coéquipier majeur est OUT — l&apos;usage de ces joueurs devrait grimper ce soir.
        </p>

        <div className="flex flex-col gap-1.5 relative">
          {opportunities.map((rec) => {
            const { player, game } = rec;
            const isHome = player.team === game.home_team;
            const opponent = isHome ? game.away_team : game.home_team;
            return (
              <Link
                key={rec.id}
                href={`/player/${player.id}`}
                className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-white/[0.03] border border-white/5 hover:border-[color:var(--color-violet)]/40 transition-colors"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-[color:var(--color-text)] truncate">
                      {player.name}
                    </span>
                    <span className="text-[9px] font-bold tracking-[0.1em] uppercase px-1.5 py-0.5 rounded bg-[color:var(--color-violet)]/15 text-[color:var(--color-violet)] border border-[color:var(--color-violet)]/30 shrink-0">
                      ⚡ boost
                    </span>
                  </div>
                  <div className="text-[11px] text-[color:var(--color-text-mute)] mt-0.5 font-mono-num">
                    {player.team} {isHome ? "vs" : "@"} {opponent}
                    <span className="text-[color:var(--color-text-dim)] ml-1.5">
                      · rang #{rec.rank}
                    </span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-display text-2xl leading-none font-mono-num text-[color:var(--color-violet)]">
                    {rec.estimated_score.toFixed(1)}
                  </div>
                  <div className="text-[8px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)] mt-0.5">
                    Estimé
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}
