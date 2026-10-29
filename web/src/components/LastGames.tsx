import { frDayMonth } from "@/lib/date";

export type LastGame = {
  game_id: string; date: string; is_home: boolean; opponent: string | null; minutes: number;
  pts: number; reb: number; ast: number; stl: number; blk: number; tov: number;
  fgm: number; fga: number; tpm: number; tpa: number; ftm: number; fta: number; ttfl_score: number;
};

/** 5 derniers matchs éligibles du joueur : ligne de stats et score TTFL.
 *  Données publiques (game_logs), même rendu en mode public et connecté. */
export default function LastGames({ games }: { games: LastGame[] }) {
  if (games.length === 0) {
    return <p className="text-sm text-[color:var(--color-text-mute)]">Aucun match cette saison.</p>;
  }
  return (
    <ol className="flex flex-col gap-1.5">
      {games.map((g) => (
        <li key={g.game_id} className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/5">
          <div className="min-w-0">
            <div className="text-sm text-[color:var(--color-text)]">
              {frDayMonth(g.date)} · {g.is_home ? "vs" : "@"} {g.opponent ?? "?"}
              {g.minutes > 0 && <span className="text-[11px] text-[color:var(--color-text-mute)]"> · {g.minutes} min</span>}
            </div>
            {g.minutes === 0 ? (
              <div className="text-[11px] text-[color:var(--color-text-mute)]">N&apos;a pas joué</div>
            ) : (
              <>
                <div className="text-[11px] text-[color:var(--color-text-soft)] font-mono-num">
                  {g.pts} pts · {g.reb} reb · {g.ast} pd · {g.stl} int · {g.blk} ctr · {g.tov} bp
                </div>
                <div className="text-[11px] text-[color:var(--color-text-mute)] font-mono-num">
                  {g.fgm}/{g.fga} tirs · {g.tpm}/{g.tpa} à 3 pts · {g.ftm}/{g.fta} LF
                </div>
              </>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className={`font-display text-2xl leading-none font-mono-num ${g.ttfl_score < 0 ? "text-[color:var(--color-crimson)]" : "text-[color:var(--color-text)]"}`}>
              {g.ttfl_score}
            </div>
            <div className="text-[9px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mt-1">TTFL</div>
          </div>
        </li>
      ))}
    </ol>
  );
}
