export interface Player {
  id: number;
  name: string;
  team: string;
  position: string;
  injury_status: string | null;
  injury_detail: string | null;
  injury_return_date?: string | null;
  avg_ttfl_l5: number;
  avg_ttfl_l10: number;
  avg_ttfl_l20: number;
  avg_ttfl_season: number;
  stddev_ttfl: number;
  home_avg: number;
  away_avg: number;
  avg_minutes_l10: number;
  usage_rate: number;
  updated_at: string;
}

export interface Game {
  id: string;
  date: string;
  season: string;
  game_type: string;
  home_team: string;
  away_team: string;
  tip_off: string | null;
  game_number: number | null;
  status: string;
  home_score: number | null;
  away_score: number | null;
}

export interface Night {
  date: string;
  season: string;
  mode: "regular" | "playoffs";
  n_eligible_games: number;
  closing_at: string;
  is_phantom: boolean;
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
  projection: number | null;
  p_play: number | null;
  value: number | null;
  lock_value: number | null;
  locked_until: string | null;
  best_future: string | null;
}

export interface WatchlistEntry {
  player_id: number;
  priority: 1 | 2 | 3;
  created_at: string;
}

export interface Pick {
  id: number;
  player_id: number;
  game_id: string;
  date: string;
  season: string;
  mode: "regular" | "playoffs";
  is_x2: boolean;
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

export interface MatchupSeasonRow {
  def_player_name: string | null;
  minutes: number;
  points: number;
  games: number;
}

/** Vue publique `standings` (migration 027) : classement Est/Ouest calculé
 *  depuis `games`, saison régulière (NBA Cup comprise, finale exclue). */
export interface StandingsRow {
  season: string;
  conference: "Est" | "Ouest";
  team: string;
  wins: number;
  losses: number;
  pct: number;
  games_behind: number;
  home_wins: number;
  home_losses: number;
  away_wins: number;
  away_losses: number;
  last10_wins: number;
  last10_losses: number;
  streak: string;
  rank: number;
}

/** `team_elo` (migration 030, mode connecté uniquement). */
export interface TeamElo {
  team: string;
  rating: number;
  games: number;
  updated_at: string;
}

/** `game_predictions` (migration 030, mode connecté uniquement). */
export interface GamePrediction {
  game_id: string;
  home_rating: number;
  away_rating: number;
  home_win_prob: number;
  expected_margin: number;
  updated_at: string;
}

export interface RecommendationWithPlayer extends Recommendation {
  player: Player;
  game: Game;
  defender?: { name: string; share: number; per36: number | null; games: number } | null;
}

