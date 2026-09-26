import { supabase } from "@/lib/supabase/public";
import { addDays, deckDate } from "@/lib/date";
import { Night, Player } from "@/types";
import DeckNight from "@/components/DeckNight";

export const revalidate = 0;

type PlanRow = { night: string; player_id: number; projection: number; explanation: string };
type PickRow = { date: string; player_id: number; is_x2: boolean; game_id: string };

export default async function DeckPage() {
  const today = deckDate();
  const until = addDays(today, 14);
  const [nightsRes, planRes, picksRes] = await Promise.all([
    supabase.from("nights").select("*").gte("date", today).lte("date", until).order("date"),
    supabase.from("plan_latest").select("night, player_id, projection, explanation").gte("night", today).lte("night", until),
    supabase.from("picks").select("date, player_id, is_x2, game_id").gte("date", today).lte("date", until),
  ]);
  const nights = (nightsRes.data || []) as Night[];
  const plan = (planRes.data || []) as PlanRow[];
  const picks = (picksRes.data || []) as PickRow[];
  const ids = [...new Set([...plan.map((p) => p.player_id), ...picks.map((p) => p.player_id)])];
  const playersRes = ids.length ? await supabase.from("players").select("*").in("id", ids) : { data: [] };
  const players = new Map(((playersRes.data || []) as Player[]).map((p) => [p.id, p]));

  // Match de l'équipe du joueur suggéré, pour réserver en un clic.
  const gamesRes = await supabase.from("games").select("id, date, home_team, away_team").gte("date", today).lte("date", until);
  const games = (gamesRes.data || []) as { id: string; date: string; home_team: string; away_team: string }[];

  return (
    <div className="px-4 py-5 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        DE<span className="flame-text">CK</span>
      </h1>
      <p className="text-[11px] text-[color:var(--color-text-mute)] mt-1 uppercase tracking-[0.18em]">
        14 prochaines soirées · suggestions du plan (indicatives)
      </p>
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
              suggestion={s && sPlayer && sGame ? { playerId: sPlayer.id, name: sPlayer.name, team: sPlayer.team, gameId: sGame.id, projection: s.projection, explanation: s.explanation } : null} />
          );
        })}
        {nights.length === 0 && <p className="text-sm text-[color:var(--color-text-mute)]">Aucune soirée TTFL dans les 14 prochains jours.</p>}
      </div>
    </div>
  );
}
