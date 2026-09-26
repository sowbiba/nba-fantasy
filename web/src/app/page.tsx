import { supabase } from "@/lib/supabase/public";
import { Game, Night, Pick, Player, Recommendation, RecommendationWithPlayer, SyncLog } from "@/types";
import SyncStatus from "@/components/SyncStatus";
import NoPickBanner from "@/components/NoPickBanner";
import GamesCollapsible from "@/components/GamesCollapsible";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";
import RefreshButton from "@/components/RefreshButton";
import MyPickCard from "@/components/MyPickCard";
import { deckDate, frLongDate, parisTime } from "@/lib/date";
import { homeState } from "@/lib/display";

export const revalidate = 0;

// Garde-fou d'affichage (pas une règle) : un joueur passé « Out » après la
// dernière synchro ne doit pas rester en tête. Miroir de HARD_OUT_STATUSES
// (engine/stats/availability_prob.py).
const HARD_OUT_STATUSES = new Set(["Out", "Doubtful", "Out For Season", "Suspended"]);
// Affichage seulement (R10) : la base refuse un x2 hors fenêtre (check
// picks_x2_window, migration 021), ce set ne fait que masquer le bouton.
const X2_MONTHS = new Set([11, 12, 1, 2, 3, 4]);

async function getData() {
  const deck = deckDate();
  const [nightRes, gamesRes, recsRes, pickRes, syncRes] = await Promise.all([
    supabase.from("nights").select("*").eq("date", deck).maybeSingle(),
    supabase.from("games").select("*").eq("date", deck).order("tip_off"),
    supabase.from("recommendations").select("*").eq("date", deck).order("rank"),
    supabase.from("picks").select("*").eq("date", deck).maybeSingle(),
    supabase.from("sync_log").select("*").eq("job", "daily_sync").order("started_at", { ascending: false }).limit(1),
  ]);
  const night = (nightRes.data as Night | null) ?? null;
  const games = ((gamesRes.data || []) as Game[]).filter((g) =>
    // Miroir de ELIGIBLE_TYPES (engine/rules/game_types.py, R4).
    ["regular", "cup_final", "playoffs"].includes(g.game_type));
  const recs = (recsRes.data || []) as Recommendation[];
  const pick = (pickRes.data as Pick | null) ?? null;

  const ids = [...new Set([...recs.map((r) => r.player_id), ...(pick ? [pick.player_id] : [])])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [] };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  const recsWithPlayers = recs
    .map((r) => {
      const player = players.get(r.player_id);
      const game = games.find((g) => g.home_team === player?.team || g.away_team === player?.team);
      if (!player || !game || (player.injury_status && HARD_OUT_STATUSES.has(player.injury_status))) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  return {
    deck, night, games, recsWithPlayers, pick,
    pickPlayer: pick ? players.get(pick.player_id) ?? null : null,
    sync: (syncRes.data?.[0] || null) as SyncLog | null,
  };
}

export default async function TonightPage() {
  const { deck, night, games, recsWithPlayers, pick, pickPlayer, sync } = await getData();
  const state = homeState({ hasNight: !!night && night.n_eligible_games > 0, recCount: recsWithPlayers.length, hasPick: !!pick });
  const top3 = recsWithPlayers.slice(0, 3);
  const month = Number(deck.slice(5, 7));

  return (
    <div className="animate-fade-in">
      <header className="relative overflow-hidden px-4 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3 relative">
          <div className="min-w-0">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-gold)] animate-live-dot" />
              {night?.mode === "playoffs" ? "Playoffs" : "Saison régulière"}
              {night && <> · fermeture {parisTime(night.closing_at)}</>}
            </span>
            <h1 className="font-display text-5xl leading-none tracking-wide text-white">
              CE <span className="flame-text">SOIR</span>
            </h1>
            <p className="text-xs text-[color:var(--color-text-mute)] mt-1.5 capitalize tracking-wide">
              {frLongDate(deck)} ·{" "}
              <span className="text-[color:var(--color-text-soft)] font-semibold">
                {games.length} match{games.length > 1 ? "s" : ""}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 pt-1">
            <RefreshButton />
          </div>
        </div>
      </header>

      {pick && pickPlayer ? (
        <MyPickCard key={`${pick.id}-${pick.is_x2}`} date={deck} playerId={pickPlayer.id} playerName={pickPlayer.name} team={pickPlayer.team}
                    isX2={pick.is_x2} x2Allowed={pick.mode === "regular" && X2_MONTHS.has(month)} />
      ) : (
        <NoPickBanner hasGamesTonight={state !== "no_games"} hasPickToday={false} />
      )}

      <SyncStatus sync={sync} />

      <div className="mt-3 px-3">
        <GamesCollapsible games={games} />
      </div>

      <section id="top-3" className="mt-6 px-3">
        <div className="flex items-end justify-between mb-3 px-1">
          <h2 className="font-display text-3xl tracking-wide text-white leading-none">
            TOP <span className="gold-text">3</span>
          </h2>
          <span className="text-[10px] tracking-[0.2em] uppercase text-[color:var(--color-text-mute)] pb-1">
            {state === "picked" ? "Alternatives pour remplacer" : "Picks du soir"}
          </span>
        </div>
        <div className="flex flex-col gap-3 stagger">
          {top3.map((rec) => <RecommendationCard key={rec.id} rec={rec} />)}
          {top3.length === 0 && (
            <div className="surface p-8 text-center">
              <div className="font-display text-2xl text-[color:var(--color-text-mute)] mb-1">
                {state === "no_games" ? "Pas de soirée TTFL" : "Aucune reco"}
              </div>
              <p className="text-sm text-[color:var(--color-text-mute)]">
                {state === "no_games" ? "Aucun match éligible ce soir." : "Prochaine synchro en cours…"}
              </p>
            </div>
          )}
        </div>
      </section>

      <PlayerList recs={recsWithPlayers} />
    </div>
  );
}
