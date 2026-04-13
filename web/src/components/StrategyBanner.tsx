import { Recommendation } from "@/types";

interface Props {
  recommendations: Recommendation[];
  gamesDaysRemaining: number;
}

export default function StrategyBanner({ recommendations, gamesDaysRemaining }: Props) {
  const elites = recommendations.filter((r) => r.tier === "elite").length;
  const solids = recommendations.filter((r) => r.tier === "solid").length;
  const fillers = recommendations.filter((r) => r.tier === "filler").length;

  return (
    <div className="mx-3 bg-gray-900 border-l-[3px] border-amber-500 rounded-r-lg px-3 py-2.5">
      <div className="text-amber-500 text-xs font-bold mb-0.5">📊 STRATÉGIE</div>
      <div className="text-gray-400 text-sm">
        {elites} elites · {solids} solides · {fillers} fillers restants — ~{gamesDaysRemaining} jours de match estimés
      </div>
    </div>
  );
}
