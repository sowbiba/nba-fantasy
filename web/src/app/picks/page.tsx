import { supabase } from "@/lib/supabase";
import { Pick, Player } from "@/types";
import PicksTabs from "./PicksTabs";

export const revalidate = 0;

async function getData() {
  const [picksRes, playersRes] = await Promise.all([
    supabase.from("picks").select("*").order("date", { ascending: false }),
    supabase.from("players").select("id, name, team"),
  ]);
  const picks = (picksRes.data || []) as Pick[];
  const players = (playersRes.data || []) as Player[];
  const playersMap = Object.fromEntries(players.map((p) => [p.id, p]));
  return { picks, playersMap };
}

export default async function PicksPage() {
  const { picks, playersMap } = await getData();

  return <PicksTabs picks={picks} playersMap={playersMap} />;
}
