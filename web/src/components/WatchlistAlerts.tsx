import Link from "next/link";
import { RecommendationWithPlayer, WatchlistEntry, Pick } from "@/types";

type AlertEntry = {
  rec: RecommendationWithPlayer;
  priority: 1 | 2 | 3;
  elimination: "critical" | "high";
};

export default function WatchlistAlerts({
  recommendations,
  watchlist,
  picks,
}: {
  recommendations: RecommendationWithPlayer[];
  watchlist: WatchlistEntry[];
  picks: Pick[];
}) {
  const byPriority = new Map(watchlist.map((w) => [w.player_id, w.priority]));
  const pickedIds = new Set(
    picks.filter((p) => p.mode === "playoffs").map((p) => p.player_id)
  );

  const alerts: AlertEntry[] = [];
  for (const rec of recommendations) {
    const priority = byPriority.get(rec.player_id);
    if (!priority) continue;
    if (pickedIds.has(rec.player_id)) continue;
    const tags = rec.tags ?? [];
    let elimination: "critical" | "high" | null = null;
    if (tags.includes("elimination_critical")) elimination = "critical";
    else if (tags.includes("elimination_high")) elimination = "high";
    if (!elimination) continue;
    alerts.push({ rec, priority, elimination });
  }

  if (alerts.length === 0) return null;

  alerts.sort((a, b) => {
    const elimOrder = { critical: 0, high: 1 };
    if (elimOrder[a.elimination] !== elimOrder[b.elimination]) {
      return elimOrder[a.elimination] - elimOrder[b.elimination];
    }
    return a.priority - b.priority;
  });

  return (
    <section className="mt-3 px-3">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold tracking-[0.22em] uppercase text-[color:var(--color-crimson)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-crimson)] animate-pulse-red" />
          Alertes capital
        </span>
        <span className="text-[10px] text-[color:var(--color-text-mute)]">
          · {alerts.length} must-play à risque
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {alerts.map(({ rec, priority, elimination }) => {
          const isCritical = elimination === "critical";
          const stars = "★".repeat(4 - priority);
          return (
            <Link
              key={rec.id}
              href={`/player/${rec.player_id}`}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-card-sm)] border transition-colors ${
                isCritical
                  ? "bg-[color:var(--color-crimson)]/[0.08] border-[color:var(--color-crimson)]/30 animate-pulse-red"
                  : "bg-[color:var(--color-flame)]/[0.05] border-[color:var(--color-flame)]/20"
              }`}
            >
              <span
                className={`font-mono-num tracking-widest text-sm ${
                  isCritical
                    ? "text-[color:var(--color-crimson)]"
                    : "text-[color:var(--color-gold)]"
                }`}
              >
                {stars}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-[color:var(--color-text)] truncate">
                  {rec.player.name}
                </div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)] mt-0.5">
                  {rec.player.team} ·{" "}
                  <span
                    className={
                      isCritical
                        ? "text-[color:var(--color-crimson)] font-bold"
                        : "text-[color:var(--color-flame)] font-bold"
                    }
                  >
                    {isCritical
                      ? "élimination critique"
                      : "série sous pression"}
                  </span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="font-display text-2xl leading-none font-mono-num flame-text">
                  {rec.estimated_score.toFixed(0)}
                </div>
                <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-0.5">
                  Estimé
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
