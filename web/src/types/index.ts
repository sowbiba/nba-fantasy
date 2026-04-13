export interface Player {
  id: number;
  name: string;
  team: string;
  position: string;
  injury_status: string | null;
  injury_detail: string | null;
  avg_ttfl_l5: number;
  avg_ttfl_l10: number;
  avg_ttfl_l20: number;
  avg_ttfl_season: number;
  stddev_ttfl: number;
  home_avg: number;
  away_avg: number;
  usage_rate: number;
  updated_at: string;
}

export interface Game {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  tip_off: string | null;
  series_id: number | null;
  game_number: number | null;
  status: string;
}

export interface Series {
  id: number;
  round: number;
  home_team: string;
  away_team: string;
  home_wins: number;
  away_wins: number;
  status: string;
}

export interface Recommendation {
  id: number;
  date: string;
  player_id: number;
  rank: number;
  estimated_score: number;
  perf_score: number;
  matchup_score: number;
  strategy_score: number | null;
  pros: string[];
  cons: string[];
  verdict: string;
  tier: "elite" | "solid" | "filler";
  tags: string[];
  computed_at: string;
}

export interface Pick {
  id: number;
  player_id: number;
  game_id: string;
  date: string;
  mode: "regular" | "playoffs";
  estimated_score: number | null;
  actual_score: number | null;
  picked_at: string;
}

export interface SyncLog {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  players_updated: number;
  error_message: string | null;
}

export interface RecommendationWithPlayer extends Recommendation {
  player: Player;
  game: Game;
}
