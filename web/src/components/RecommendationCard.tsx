import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

const rankColors: Record<number, string> = {
  1: "bg-green-500 text-gray-950",
  2: "bg-blue-500 text-gray-950",
  3: "bg-purple-500 text-gray-950",
};

const rankBorders: Record<number, string> = {
  1: "border-l-green-500",
  2: "border-l-blue-500",
  3: "border-l-purple-500",
};

const tierBadges: Record<string, { bg: string; text: string; label: string }> = {
  elite: { bg: "bg-green-500", text: "text-gray-950", label: "★★★ ELITE" },
  solid: { bg: "bg-blue-500", text: "text-gray-950", label: "★★ SOLIDE" },
  filler: { bg: "bg-gray-600", text: "text-gray-200", label: "★ FILLER" },
};

export default function RecommendationCard({ rec }: { rec: RecommendationWithPlayer }) {
  const { player, game, rank } = rec;
  const isHome = player.team === game.home_team;
  const opponent = isHome ? game.away_team : game.home_team;
  const tier = tierBadges[rec.tier] || tierBadges.filler;

  return (
    <Link href={`/player/${player.id}`} className="block text-gray-100">
      <div className={`bg-gray-900 rounded-xl p-3 border-l-[3px] ${rankBorders[rank] || "border-l-gray-600"}`}>
        <div className="flex justify-between items-start">
          <div className="flex gap-2.5 items-center">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${rankColors[rank] || "bg-gray-600 text-gray-200"}`}>
              {rank}
            </div>
            <div>
              <div className="font-bold text-[0.95em] text-gray-100">{player.name}</div>
              <div className="text-gray-500 text-xs">
                {isHome ? `${player.team} vs ${opponent}` : `${player.team} @ ${opponent}`}
                {game.game_number ? ` · Game ${game.game_number}` : ""}
                {isHome ? " · 🏠 Domicile" : " · ✈️ Extérieur"}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className={`font-bold text-lg ${rank === 1 ? "text-green-500" : rank === 2 ? "text-blue-400" : "text-purple-400"}`}>
              {rec.estimated_score.toFixed(1)}
            </div>
            <div className="text-gray-600 text-[0.65em]">score estimé</div>
          </div>
        </div>
        <p className="text-gray-400 text-[0.78em] mt-2 leading-relaxed line-clamp-2">
          {rec.pros[0] || rec.verdict.split(".")[0]}
          {rec.cons[0] ? ` ⚠️ ${rec.cons[0]}` : ""}
        </p>
        <div className="flex gap-1.5 mt-2 flex-wrap">
          <span className={`${tier.bg} ${tier.text} text-[0.65em] px-2 py-0.5 rounded-full font-bold`}>{tier.label}</span>
          {rec.tags.includes("hot") && <span className="bg-green-950 text-green-500 text-[0.65em] px-2 py-0.5 rounded-full">🔥 En forme</span>}
          {rec.tags.includes("home") && <span className="bg-blue-950 text-blue-400 text-[0.65em] px-2 py-0.5 rounded-full">🏠 Home</span>}
          {rec.tags.includes("volatile") && <span className="bg-red-950 text-red-400 text-[0.65em] px-2 py-0.5 rounded-full">🎲 Volatile</span>}
          {rec.tags.includes("elimination_critical") && <span className="bg-red-600 text-white text-[0.65em] px-2 py-0.5 rounded-full font-bold">🚨 ÉLIMINATION</span>}
          {rec.tags.includes("elimination_high") && <span className="bg-amber-700 text-amber-100 text-[0.65em] px-2 py-0.5 rounded-full">⚠️ Série critique</span>}
          {rec.tags.includes("teammate_out") && <span className="bg-purple-950 text-purple-400 text-[0.65em] px-2 py-0.5 rounded-full">⚡ Usage boost</span>}
        </div>
      </div>
    </Link>
  );
}
