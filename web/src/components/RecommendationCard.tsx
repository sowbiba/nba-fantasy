import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

/**
 * Hero card for a Top-3 recommendation.
 * Rank-specific chrome: #1 = flame/gold, #2 = ice blue, #3 = violet.
 */

type RankStyle = {
  gradient: string;
  ring: string;
  rankText: string;
  accent: string;
  scoreText: string;
  label: string;
};

const rankStyles: Record<number, RankStyle> = {
  1: {
    gradient:
      "linear-gradient(135deg, rgba(255, 91, 31, 0.18) 0%, rgba(247, 201, 72, 0.10) 35%, rgba(20, 20, 27, 0.92) 75%)",
    ring: "border-[color:var(--color-flame)]/35",
    rankText: "text-white",
    accent: "bg-[color:var(--color-flame)]",
    scoreText: "flame-text",
    label: "PICK #1",
  },
  2: {
    gradient:
      "linear-gradient(135deg, rgba(92, 199, 255, 0.14) 0%, rgba(20, 20, 27, 0.92) 70%)",
    ring: "border-[color:var(--color-ice)]/30",
    rankText: "text-white",
    accent: "bg-[color:var(--color-ice)]",
    scoreText: "text-[color:var(--color-ice)]",
    label: "PICK #2",
  },
  3: {
    gradient:
      "linear-gradient(135deg, rgba(167, 139, 250, 0.14) 0%, rgba(20, 20, 27, 0.92) 70%)",
    ring: "border-[color:var(--color-violet)]/30",
    rankText: "text-white",
    accent: "bg-[color:var(--color-violet)]",
    scoreText: "text-[color:var(--color-violet)]",
    label: "PICK #3",
  },
};

const tierBadges: Record<
  string,
  { classes: string; label: string; stars: string }
> = {
  elite: {
    classes:
      "bg-[color:var(--color-gold)]/15 text-[color:var(--color-gold-soft)] border border-[color:var(--color-gold)]/40",
    label: "ELITE",
    stars: "★★★",
  },
  solid: {
    classes:
      "bg-[color:var(--color-ice)]/12 text-[color:var(--color-ice)] border border-[color:var(--color-ice)]/35",
    label: "SOLIDE",
    stars: "★★",
  },
  filler: {
    classes:
      "bg-white/5 text-[color:var(--color-text-soft)] border border-white/10",
    label: "FILLER",
    stars: "★",
  },
};

function TagChip({
  children,
  tone,
  pulse,
}: {
  children: React.ReactNode;
  tone: string;
  pulse?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-bold tracking-[0.08em] px-2 py-0.5 rounded-full ${tone} ${
        pulse ? "animate-pulse-red" : ""
      }`}
    >
      {children}
    </span>
  );
}

export default function RecommendationCard({
  rec,
}: {
  rec: RecommendationWithPlayer;
}) {
  const { player, game, rank } = rec;
  const isHome = player.team === game.home_team;
  const opponent = isHome ? game.away_team : game.home_team;
  const style = rankStyles[rank] || rankStyles[3];
  const tier = tierBadges[rec.tier] || tierBadges.filler;
  const isElimCritical = rec.tags.includes("elimination_critical");

  return (
    <Link
      href={`/player/${player.id}`}
      className="group block focus:outline-none"
    >
      <article
        className={`relative overflow-hidden rounded-[var(--radius-card)] border ${style.ring} transition-transform active:scale-[0.99]`}
        style={{
          background: style.gradient,
          boxShadow:
            rank === 1
              ? "var(--shadow-flame)"
              : "var(--shadow-card)",
        }}
      >
        {/* top accent bar */}
        <div className={`h-[3px] w-full ${style.accent}`} />

        {/* rank watermark */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-4 -top-4 select-none"
        >
          <span className="font-display text-[160px] leading-none text-white/[0.04] tracking-tighter">
            {rank}
          </span>
        </div>

        {/* court arc decoration for rank 1 */}
        {rank === 1 && (
          <svg
            aria-hidden
            className="absolute -bottom-10 -left-8 w-48 h-48 opacity-[0.08] pointer-events-none"
            viewBox="0 0 200 200"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
          >
            <circle
              cx="100"
              cy="100"
              r="90"
              className="text-[color:var(--color-flame)]"
            />
            <circle
              cx="100"
              cy="100"
              r="55"
              className="text-[color:var(--color-gold)]"
            />
          </svg>
        )}

        <div className="relative p-4">
          {/* top row: rank + label / score */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex flex-col items-center">
                <span
                  className={`text-[9px] tracking-[0.25em] font-bold uppercase text-[color:var(--color-text-mute)]`}
                >
                  {style.label}
                </span>
                <span className="font-display text-[56px] leading-[0.9] text-white font-mono-num">
                  {rank}
                </span>
              </div>
              <div className="min-w-0 pt-1">
                <h3 className="font-display text-2xl text-white tracking-wide leading-tight truncate">
                  {player.name}
                </h3>
                <p className="text-xs text-[color:var(--color-text-soft)] mt-0.5 tracking-wide">
                  <span className="font-semibold text-[color:var(--color-text)]">
                    {player.team}
                  </span>
                  <span className="text-[color:var(--color-text-mute)] mx-1.5">
                    {isHome ? "vs" : "@"}
                  </span>
                  <span className="font-semibold">{opponent}</span>
                  {game.game_number && (
                    <span className="ml-1.5 text-[color:var(--color-gold)]">
                      · G{game.game_number}
                    </span>
                  )}
                </p>
                <p className="text-[10px] text-[color:var(--color-text-mute)] mt-0.5 uppercase tracking-[0.2em]">
                  {isHome ? "Domicile" : "Extérieur"} · {player.position}
                </p>
              </div>
            </div>

            <div className="text-right shrink-0">
              <div
                className={`font-display text-5xl leading-none font-mono-num ${style.scoreText}`}
              >
                {rec.estimated_score.toFixed(0)}
                <span className="text-xl align-top opacity-60">
                  .{rec.estimated_score.toFixed(1).split(".")[1]}
                </span>
              </div>
              <div className="text-[9px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)] mt-0.5">
                Score estimé
              </div>
            </div>
          </div>

          {/* verdict line */}
          <p className="text-sm text-[color:var(--color-text-soft)] mt-3 leading-snug line-clamp-2">
            {rec.pros[0] || rec.verdict.split(".")[0]}
            {rec.cons[0] ? (
              <span className="text-[color:var(--color-text-mute)]">
                {" "}
                — <span className="text-[color:var(--color-flame-soft)]">⚠</span>{" "}
                {rec.cons[0]}
              </span>
            ) : null}
          </p>

          {/* badges */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            <span
              className={`inline-flex items-center gap-1 text-[10px] font-bold tracking-[0.1em] px-2 py-0.5 rounded-full ${tier.classes}`}
            >
              <span>{tier.stars}</span>
              <span>{tier.label}</span>
            </span>

            {isElimCritical && (
              <TagChip
                tone="bg-[color:var(--color-crimson)] text-white"
                pulse
              >
                ELIMINATION
              </TagChip>
            )}
            {rec.tags.includes("elimination_high") && (
              <TagChip tone="bg-amber-500/20 text-amber-300 border border-amber-400/40">
                SERIE CRITIQUE
              </TagChip>
            )}
            {rec.tags.includes("teammate_out") && (
              <TagChip tone="bg-[color:var(--color-violet)]/15 text-[color:var(--color-violet)] border border-[color:var(--color-violet)]/35">
                USAGE+
              </TagChip>
            )}
            {rec.tags.includes("hot") && (
              <TagChip tone="bg-[color:var(--color-emerald)]/15 text-[color:var(--color-emerald)] border border-[color:var(--color-emerald)]/30">
                EN FORME
              </TagChip>
            )}
            {rec.tags.includes("home") && (
              <TagChip tone="bg-white/5 text-[color:var(--color-text-soft)] border border-white/10">
                HOME
              </TagChip>
            )}
            {rec.tags.includes("volatile") && (
              <TagChip tone="bg-[color:var(--color-crimson)]/10 text-[color:var(--color-crimson)]/90 border border-[color:var(--color-crimson)]/25">
                VOLATILE
              </TagChip>
            )}
          </div>
        </div>
      </article>
    </Link>
  );
}
