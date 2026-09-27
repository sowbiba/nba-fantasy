import { supabase } from "@/lib/supabase/public";
import { addDays, deckDate } from "@/lib/date";
import { Night, Player } from "@/types";
import DeckNight from "@/components/DeckNight";

export const revalidate = 0;

type PlanRow = { night: string; player_id: number; projection: number; explanation: string; is_x2: boolean };
type PickRow = { date: string; player_id: number; is_x2: boolean; game_id: string };

export default async function DeckPage() {
  const today = deckDate();
  const until = addDays(today, 14);
  const [nightsRes, planRes, picksRes] = await Promise.all([
    supabase.from("nights").select("*").gte("date", today).lte("date", until).order("date"),
    supabase.from("plan_latest").select("night, player_id, projection, explanation, is_x2").gte("night", today).lte("night", until),
    supabase.from("picks").select("date, player_id, is_x2, game_id").gte("date", today).lte("date", until),
  ]);
  const nights = (nightsRes.data || []) as Night[];
  const plan = (planRes.data || []) as PlanRow[];
  const picks = (picksRes.data || []) as PickRow[];
  const ids = [...new Set([...plan.map((p) => p.player_id), ...picks.map((p) => p.player_id)])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [], error: null };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  // Match de l'équipe du joueur suggéré, pour réserver en un clic.
  const gamesRes = await supabase.from("games").select("id, date, home_team, away_team")
    .gte("date", today).lte("date", until)
    // Miroir de ELIGIBLE_TYPES (engine/rules/game_types.py, R4).
    .in("game_type", ["regular", "cup_final", "playoffs"]);
  const games = (gamesRes.data || []) as { id: string; date: string; home_team: string; away_team: string }[];
  const dataError = [nightsRes, planRes, picksRes, playersRes, gamesRes].some((r) => r.error);

  return (
    <div className="px-4 py-5 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        DE<span className="flame-text">CK</span>
      </h1>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1 uppercase tracking-[0.18em]">
        Les soirées des 14 prochains jours · suggestions du plan (indicatives)
      </p>
      {dataError && (
        <p role="alert" className="mt-3 rounded-[var(--radius-card-sm)] border border-[color:var(--color-crimson)]/40 bg-[color:var(--color-crimson)]/10 px-3 py-2 text-sm text-[color:var(--color-crimson)]">
          Données indisponibles pour le moment, réessaie dans quelques minutes.
        </p>
      )}
      <div className="mt-4 flex flex-col gap-2">
        {nights.map((n) => {
          const pick = picks.find((p) => p.date === n.date);
          const pickPlayer = pick ? players.get(pick.player_id) : undefined;
          const s = plan.find((p) => p.night === n.date);
          const sPlayer = s ? players.get(s.player_id) : undefined;
          const sGame = sPlayer ? games.find((g) => g.date === n.date && (g.home_team === sPlayer.team || g.away_team === sPlayer.team)) : undefined;
          return (
            <DeckNight key={n.date} date={n.date} closingAt={n.closing_at} nGames={n.n_eligible_games}
              isPhantom={n.is_phantom} isToday={n.date === today}
              pick={pick && pickPlayer ? { playerId: pickPlayer.id, name: pickPlayer.name, team: pickPlayer.team, injury: pickPlayer.injury_status, isX2: pick.is_x2 } : null}
              suggestion={s && sPlayer && sGame ? { playerId: sPlayer.id, name: sPlayer.name, team: sPlayer.team, gameId: sGame.id, projection: s.projection, explanation: s.explanation, isX2: s.is_x2 } : null} />
          );
        })}
        {nights.length === 0 && !dataError && <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL dans les 14 prochains jours.</p>}
      </div>
    </div>
  );
}
