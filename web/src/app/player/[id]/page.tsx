import { supabase } from "@/lib/supabase/public";
import { ownerDb } from "@/lib/viewer";
import { Player, Recommendation, WatchlistEntry } from "@/types";
import { ProsBlock, ConsBlock, VerdictBlock } from "@/components/ProsCons";
import BackButton from "./BackButton";
import WatchlistStar from "./WatchlistStar";
import PickControls, { CalendarNight } from "./PickControls";
import { deckDate, addDays } from "@/lib/date";
import { HARD_OUT_STATUSES, recMeta } from "@/lib/display";

export const revalidate = 0;

const tierLabels: Record<
  string,
  { label: string; color: string; stars: string }
> = {
  elite: {
    label: "ELITE",
    color: "text-[color:var(--color-gold)]",
    stars: "★★★",
  },
  solid: {
    label: "SOLIDE",
    color: "text-[color:var(--color-ice)]",
    stars: "★★",
  },
  filler: {
    label: "FILLER",
    color: "text-[color:var(--color-text-soft)]",
    stars: "★",
  },
};

async function getData(playerId: number) {
  const today = deckDate();
  const until = addDays(today, 29);
  const db = await ownerDb();
  // recommendations, player_calendar, player_watchlist et picks sont des
  // données TTFL privées (migration 028) : en mode public (db === null),
  // on ne les interroge pas — la fiche publique (tâche 5) affiche seulement
  // les données publiques ci-dessous (players).
  const emptySingle: { data: null; error: null } = { data: null, error: null };
  const emptyList: { data: never[]; error: null } = { data: [], error: null };
  const [playerRes, recRes, calRes, watchlistRes, picksRes] = await Promise.all([
    supabase.from("players").select("*").eq("id", playerId).single(),
    db
      ? db.from("recommendations").select("*").eq("player_id", playerId).eq("date", today).maybeSingle()
      : emptySingle,
    db
      ? db.rpc("player_calendar", { p_player_id: playerId, p_from: today, p_to: until })
      : emptyList,
    db
      ? db.from("player_watchlist").select("*").eq("player_id", playerId).maybeSingle()
      : emptySingle,
    // Le pick déjà posé (par ce joueur ou un autre) sur chaque soirée du calendrier (M2).
    db
      ? db.from("picks").select("date, player_id, players(name)").gte("date", today).lte("date", until)
      : emptyList,
  ]);
  type PickWithPlayer = { date: string; player_id: number; players: { name: string } | null };
  const picksByDate: Record<string, { playerId: number; name: string }> = {};
  for (const p of (picksRes.data || []) as unknown as PickWithPlayer[]) {
    picksByDate[p.date] = { playerId: p.player_id, name: p.players?.name ?? `#${p.player_id}` };
  }
  return {
    today,
    player: playerRes.data as Player | null,
    rec: (recRes.data as Recommendation | null) ?? null,
    nights: (calRes.data || []) as CalendarNight[],
    watchlist: (watchlistRes.data as WatchlistEntry | null) ?? null,
    picksByDate,
  };
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const playerId = parseInt(id, 10);
  const { today, player, rec, nights, watchlist, picksByDate } = await getData(playerId);

  if (!player) {
    return (
      <div className="px-4 py-12 text-center">
        <div className="font-display text-3xl text-[color:var(--color-text-mute)]">
          Joueur
          <br />
          introuvable
        </div>
      </div>
    );
  }

  const tonight = nights.find((n) => n.night === today);
  const tier = tierLabels[rec?.tier || "filler"];
  const estimatedScore = rec?.estimated_score;
  const pros = rec?.pros ?? [];
  const cons = rec?.cons ?? [];
  const verdict = rec?.verdict ?? "";
  const hasArgumentaire = !!rec;
  const meta = rec ? recMeta(rec) : null;

  return (
    <div className="px-4 py-4 animate-fade-in">
      <BackButton />

      {/* ----------------- identity header ----------------- */}
      <header className="mt-3 relative">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs ${tier.color}`}>{tier.stars}</span>
              <span
                className={`text-[10px] uppercase tracking-[0.22em] font-bold ${tier.color}`}
              >
                {tier.label}
              </span>
              <WatchlistStar
                playerId={playerId}
                initialPriority={
                  (watchlist?.priority as 1 | 2 | 3 | undefined) ?? null
                }
              />
            </div>
            <h1 className="font-display text-4xl leading-none tracking-wide text-white">
              {player.name}
            </h1>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mt-2 text-sm">
              <span className="font-bold text-[color:var(--color-flame)] tracking-wide">
                {player.team}
              </span>
              <span className="text-[color:var(--color-text-mute)]">·</span>
              <span className="text-[color:var(--color-text-soft)]">
                {player.position}
              </span>
              {tonight && (
                <>
                  <span className="text-[color:var(--color-text-mute)]">·</span>
                  <span className="text-[color:var(--color-text-soft)]">
                    {tonight.is_home ? "vs" : "@"}{" "}
                    <span className="font-bold text-[color:var(--color-text)]">
                      {tonight.opponent}
                    </span>
                  </span>
                </>
              )}
            </div>
          </div>

          {estimatedScore !== undefined && (
            <div className="text-right shrink-0">
              <div className="font-display text-5xl leading-none font-mono-num flame-text">
                {estimatedScore.toFixed(1)}
              </div>
              <div className="text-[9px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mt-1">
                Espérance
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ----------------- stats block ----------------- */}
      <div className="grid grid-cols-3 gap-2 mt-5">
        <StatTile
          value={player.avg_ttfl_l5?.toFixed(1) || "—"}
          label="5 derniers"
        />
        <StatTile
          value={player.avg_ttfl_season?.toFixed(1) || "—"}
          label="Saison"
        />
        <StatTile
          value={
            player.avg_ttfl_season
              ? `${Math.round(
                  player.avg_ttfl_season - player.stddev_ttfl
                )}·${Math.round(player.avg_ttfl_season + player.stddev_ttfl)}`
              : "—"
          }
          label="Floor · Ceiling"
          mono
        />
      </div>

      {/* ----------------- pros / cons / verdict ----------------- */}
      {hasArgumentaire && (
        <div className="flex flex-col gap-3 mt-5">
          {pros.length > 0 && <ProsBlock pros={pros} />}
          {cons.length > 0 && <ConsBlock cons={cons} />}
          {verdict && <VerdictBlock verdict={verdict} />}
          {meta && (meta.pPlay || meta.lockedUntil) && (
            <p className="text-[11px] tracking-wide text-[color:var(--color-text-mute)]">
              {meta.pPlay && (
                <>
                  Joue à{" "}
                  <span className="text-[color:var(--color-text-soft)] font-semibold">
                    {meta.pPlay}
                  </span>
                </>
              )}
              {meta.value && (
                <>
                  {" "}
                  · valeur{" "}
                  <span className="text-[color:var(--color-text-soft)] font-semibold">
                    {meta.value}
                  </span>
                </>
              )}
              {meta.lockedUntil && <> · bloqué jusqu&apos;au {meta.lockedUntil}</>}
              {meta.bestFuture && (
                <>
                  <br />
                  Meilleur soir à venir : {meta.bestFuture}
                </>
              )}
            </p>
          )}
        </div>
      )}

      {player.injury_status && (
        <p role="status" className={`mt-4 px-3 py-2 rounded-[var(--radius-card-sm)] border text-sm ${
          HARD_OUT_STATUSES.has(player.injury_status)
            ? "border-[color:var(--color-crimson)]/40 text-[color:var(--color-crimson)]"
            : "border-[color:var(--color-gold)]/40 text-[color:var(--color-gold)]"
        }`}>
          Blessé : {player.injury_status}{player.injury_detail ? ` · ${player.injury_detail}` : ""}
          {player.injury_return_date && !isNaN(new Date(player.injury_return_date).getTime()) &&
            ` · retour estimé ${new Date(player.injury_return_date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", timeZone: "Europe/Paris" })}`}
        </p>
      )}

      {/* ----------------- soirées à venir ----------------- */}
      <section className="mt-6">
        <h2 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2">
          Ses soirées (30 jours)
        </h2>
        <PickControls
          playerId={player.id}
          nights={nights}
          today={today}
          lastBookable={addDays(today, 14)}
          picksByDate={picksByDate}
          injuryStatus={player.injury_status}
        />
      </section>
    </div>
  );
}

function StatTile({
  value,
  label,
  mono = false,
}: {
  value: string;
  label: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-2 py-3 text-center">
      <div
        className={`font-display text-2xl leading-none text-white font-mono-num ${
          mono ? "text-lg" : ""
        }`}
      >
        {value}
      </div>
      <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-1.5">
        {label}
      </div>
    </div>
  );
}
