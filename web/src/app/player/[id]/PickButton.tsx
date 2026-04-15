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

export default function PickButton({
  playerId,
  gameId,
  playerName,
  estimatedScore,
  alreadyPicked,
  pickedToday,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const disabled = alreadyPicked || pickedToday || done;

  const handlePick = async () => {
    if (disabled) return;
    setLoading(true);
    const today = new Date().toISOString().split("T")[0];
    const { error } = await supabase.from("picks").insert({
      player_id: playerId,
      game_id: gameId,
      date: today,
      mode: "playoffs",
      estimated_score: estimatedScore,
      picked_at: new Date().toISOString(),
    });
    setLoading(false);
    if (!error) {
      setDone(true);
    } else {
      alert(`Erreur: ${error.message}`);
    }
  };

  // base styles
  const baseLayout =
    "relative w-full overflow-hidden rounded-[var(--radius-card)] py-4 font-display text-xl tracking-[0.15em] transition-all active:scale-[0.99]";

  let label: React.ReactNode = (
    <>
      <span className="opacity-70 text-[10px] tracking-[0.28em] block leading-none mb-1">
        Confirmer mon pick
      </span>
      PICKER · {playerName.split(" ").slice(-1)[0].toUpperCase()}
    </>
  );
  let className = `${baseLayout} text-white`;
  let inlineStyle: React.CSSProperties = {
    background:
      "linear-gradient(135deg, #ff6a2e 0%, #ff5b1f 40%, #e0420a 100%)",
    boxShadow:
      "0 14px 40px -14px rgba(255, 91, 31, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.2)",
  };

  if (done) {
    label = (
      <>
        <span className="opacity-80 text-[10px] tracking-[0.28em] block leading-none mb-1">
          Validé
        </span>
        {playerName.toUpperCase()} · PICKÉ
      </>
    );
    className = `${baseLayout} text-white`;
    inlineStyle = {
      background:
        "linear-gradient(135deg, #19c37d 0%, #0e9b62 100%)",
      boxShadow: "0 10px 30px -12px rgba(25, 195, 125, 0.5)",
    };
  } else if (alreadyPicked) {
    label = <>DÉJÀ PICKÉ EN PLAYOFFS</>;
    className = `${baseLayout} text-[color:var(--color-text-mute)]`;
    inlineStyle = {
      background: "rgba(255, 255, 255, 0.04)",
      border: "1px solid rgba(255, 255, 255, 0.06)",
      boxShadow: "none",
    };
  } else if (pickedToday) {
    label = <>TU AS DÉJÀ PICKÉ CE SOIR</>;
    className = `${baseLayout} text-[color:var(--color-text-mute)]`;
    inlineStyle = {
      background: "rgba(255, 255, 255, 0.04)",
      border: "1px solid rgba(255, 255, 255, 0.06)",
      boxShadow: "none",
    };
  }

  return (
    <button
      onClick={handlePick}
      disabled={disabled || loading}
      className={className}
      style={inlineStyle}
    >
      {/* shine effect for the active CTA */}
      {!disabled && !loading && (
        <span
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.22) 50%, transparent 70%)",
            backgroundSize: "200% 100%",
            animation: "ttfl-shine 3s ease-in-out infinite",
          }}
        />
      )}
      <span className="relative">{loading ? "..." : label}</span>
    </button>
  );
}
