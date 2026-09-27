import { supabase } from "@/lib/supabase/public";
import { Game, MatchupSeasonRow, Night, Pick, Player, Recommendation, RecommendationWithPlayer, SyncLog } from "@/types";
import SyncStatus from "@/components/SyncStatus";
import NoPickBanner from "@/components/NoPickBanner";
import GamesCollapsible from "@/components/GamesCollapsible";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";
import RefreshButton from "@/components/RefreshButton";
import MyPickCard from "@/components/MyPickCard";
import { deckDate, frLongDate, parisTime } from "@/lib/date";
import { HARD_OUT_STATUSES, homeState, topDefender, x2Hint } from "@/lib/display";

export const revalidate = 0;

// Affichage seulement (R10) : la base refuse un x2 hors fenêtre (check
// picks_x2_window, migration 021), ce set ne fait que masquer le bouton.
const X2_MONTHS = new Set([11, 12, 1, 2, 3, 4]);

type PlanRow = { night: string; player_id: number; is_x2: boolean };

async function getData() {
  const deck = deckDate();
  const [nightRes, gamesRes, recsRes, pickRes, syncRes, planRes] = await Promise.all([
    supabase.from("nights").select("*").eq("date", deck).maybeSingle(),
    supabase.from("games").select("*").eq("date", deck).order("tip_off"),
    supabase.from("recommendations").select("*").eq("date", deck).order("rank"),
    supabase.from("picks").select("*").eq("date", deck).maybeSingle(),
    supabase.from("sync_log").select("*").eq("job", "daily_sync").order("started_at", { ascending: false }).limit(1),
    supabase.from("plan_latest").select("night, player_id, is_x2").eq("night", deck).maybeSingle(),
  ]);
  const night = (nightRes.data as Night | null) ?? null;
  const plan = (planRes.data as PlanRow | null) ?? null;
  const games = ((gamesRes.data || []) as Game[]).filter((g) =>
    // Miroir de ELIGIBLE_TYPES (engine/rules/game_types.py, R4).
    ["regular", "cup_final", "playoffs"].includes(g.game_type));
  const recs = (recsRes.data || []) as Recommendation[];
  const pick = (pickRes.data as Pick | null) ?? null;

  const ids = [...new Set([...recs.map((r) => r.player_id), ...(pick ? [pick.player_id] : []), ...(plan ? [plan.player_id] : [])])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [], error: null };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  const recsWithPlayersBase = recs
    .map((r) => {
      const player = players.get(r.player_id);
      const game = games.find((g) => g.home_team === player?.team || g.away_team === player?.team);
      if (!player || !game || (player.injury_status && HARD_OUT_STATUSES.has(player.injury_status))) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  const opponentOf = (r: RecommendationWithPlayer) => r.game.home_team === r.player.team ? r.game.away_team : r.game.home_team;

  // Défenseur principal de la saison : une seule requête pour tous les joueurs recommandés (pas une par carte),
  // restreinte aux adversaires du soir pour rester légère.
  const season = night?.season;
  let defenders = new Map<string, ReturnType<typeof topDefender>>();
  let matchupError = null;
  if (season && recsWithPlayersBase.length) {
    const opponents = [...new Set(recsWithPlayersBase.map(opponentOf))];
    const { data, error } = await supabase.from("matchup_season")
      .select("player_id, opponent_team, def_player_name, minutes, points, games")
      .eq("season", season)
      .in("player_id", recsWithPlayersBase.map((r) => r.player_id))
      .in("opponent_team", opponents);
    matchupError = error;
    const byKey = new Map<string, MatchupSeasonRow[]>();
    for (const r of (data || []) as (MatchupSeasonRow & { player_id: number; opponent_team: string })[]) {
      const k = `${r.player_id}:${r.opponent_team}`;
      byKey.set(k, [...(byKey.get(k) ?? []), r]);
    }
    defenders = new Map([...byKey].map(([k, rows]) => [k, topDefender(rows)]));
  }
  const recsWithPlayers = recsWithPlayersBase.map((r) => ({
    ...r, defender: defenders.get(`${r.player_id}:${opponentOf(r)}`) ?? null,
  }));

  const dataError = [nightRes, gamesRes, recsRes, pickRes, playersRes, planRes].some((r) => r.error) || !!matchupError;

  return {
    deck, night, games, recsWithPlayers, pick, dataError, plan,
    pickPlayer: pick ? players.get(pick.player_id) ?? null : null,
    planPlayer: plan ? players.get(plan.player_id) ?? null : null,
    sync: (syncRes.data?.[0] || null) as SyncLog | null,
  };
}

export default async function TonightPage() {
  const { deck, night, games, recsWithPlayers, pick, pickPlayer, plan, planPlayer, sync, dataError } = await getData();
  const state = homeState({ hasNight: !!night && night.n_eligible_games > 0, recCount: recsWithPlayers.length, hasPick: !!pick });
  const top3 = recsWithPlayers.slice(0, 3);
  const month = Number(deck.slice(5, 7));
  const x2Allowed = (pick ? pick.mode === "regular" : night?.mode === "regular") && X2_MONTHS.has(month);
  const hint = x2Hint({ planIsX2: !!plan?.is_x2, hasPick: !!pick, pickIsX2: pick?.is_x2 ?? false, x2Allowed });
  // R10 (informatif) : le plan est indicatif — il suggère seulement le SOIR du x2, pas le joueur.
  // Le pick du moment reste le meilleur dispo ; le x2 se pose sur CE pick, pas sur le joueur du plan.
  const samePlayer = !pick || !planPlayer || pick.player_id === planPlayer.id;

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

      {dataError && (
        <div className="px-4">
          <p role="alert" className="rounded-[var(--radius-card-sm)] border border-[color:var(--color-crimson)]/40 bg-[color:var(--color-crimson)]/10 px-3 py-2 text-sm text-[color:var(--color-crimson)]">
            Données indisponibles pour le moment, réessaie dans quelques minutes.
          </p>
        </div>
      )}

      {hint && (
        <div className="mx-3 mt-3 rounded-[var(--radius-card-sm)] border border-[color:var(--color-gold)]/40 bg-[color:var(--color-gold)]/10 px-3 py-2 text-xs text-[color:var(--color-gold)]">
          {hint === "deja"
            ? "x2 activé sur ton pick, comme le suggère le plan pour ce soir."
            : !pick
              ? `Le plan suggère le x2 ce soir (il le place sur ${planPlayer?.name}). Pose ton pick puis active-le.`
              : samePlayer
                ? "Le plan suggère ton x2 ce soir."
                : `Le plan suggère le x2 ce soir (il le place sur ${planPlayer?.name}) — ça reste valable sur ton pick, active-le ci-dessous.`}
        </div>
      )}

      {pick && pickPlayer ? (
        <MyPickCard key={`${pick.id}-${pick.is_x2}`} date={deck} playerId={pickPlayer.id} playerName={pickPlayer.name} team={pickPlayer.team}
                    isX2={pick.is_x2} x2Allowed={x2Allowed} closingAt={night?.closing_at ?? ""} />
      ) : (
        !dataError && <NoPickBanner hasGamesTonight={state !== "no_games"} />
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
          {top3.length === 0 && !dataError && (
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
