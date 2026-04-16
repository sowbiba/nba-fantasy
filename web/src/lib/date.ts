/**
 * Returns the current TTFL "game day" as YYYY-MM-DD.
 *
 * The NBA schedule uses US dates: a game on "April 18" tips off at 7pm ET
 * (= 1am Paris April 19). For a French user at 3am, "ce soir" should still
 * show April 18 games (they're live right now), not April 19.
 *
 * We use America/New_York (US Eastern) as the reference timezone. The NBA
 * game day effectively flips around midnight ET (= ~6am Paris). This covers:
 *
 *   23h Paris (17h ET) → same NBA day → upcoming games
 *    2h Paris (20h ET) → same NBA day → live games
 *    5h Paris (23h ET) → same NBA day → late West Coast games
 *    7h Paris ( 1h ET) → next day    → tomorrow's games
 */
export function todayNBA(): string {
  return new Date().toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });
}

/**
 * Returns today in Paris timezone (for display / non-game-day contexts).
 */
export function todayParis(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}
