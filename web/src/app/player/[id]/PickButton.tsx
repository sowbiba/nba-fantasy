"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

interface Props {
  playerId: number;
  gameId: string;
  playerName: string;
  estimatedScore: number;
  alreadyPicked: boolean;
  pickedToday: boolean;
}

export default function PickButton({ playerId, gameId, playerName, estimatedScore, alreadyPicked, pickedToday }: Props) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const disabled = alreadyPicked || pickedToday || done;

  const handlePick = async () => {
    if (disabled) return;
    setLoading(true);
    const today = new Date().toISOString().split("T")[0];
    const { error } = await supabase.from("picks").insert({
      player_id: playerId, game_id: gameId, date: today,
      mode: "playoffs", estimated_score: estimatedScore, picked_at: new Date().toISOString(),
    });
    setLoading(false);
    if (!error) { setDone(true); } else { alert(`Erreur: ${error.message}`); }
  };

  let label = `Picker ${playerName} ce soir`;
  let className = "w-full bg-green-600 text-gray-950 rounded-xl py-3.5 font-bold text-sm";

  if (done) {
    label = `✅ ${playerName} pické !`;
    className = "w-full bg-green-900 text-green-400 rounded-xl py-3.5 font-bold text-sm";
  } else if (alreadyPicked) {
    label = "Déjà pické en playoffs";
    className = "w-full bg-gray-800 text-gray-500 rounded-xl py-3.5 font-bold text-sm";
  } else if (pickedToday) {
    label = "Tu as déjà pické quelqu'un ce soir";
    className = "w-full bg-gray-800 text-gray-500 rounded-xl py-3.5 font-bold text-sm";
  }

  return (
    <button onClick={handlePick} disabled={disabled || loading} className={className}>
      {loading ? "..." : label}
    </button>
  );
}
