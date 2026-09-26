// Miroirs de engine/io/espn.py (tricodes, normalisation, appariement).

const ESPN_ABBR_TO_TRICODE: Record<string, string> = {
  GS: "GSW",
  NY: "NYK",
  SA: "SAS",
  NO: "NOP",
  UTAH: "UTA",
  WSH: "WAS",
};

export function espnTricode(abbr: string): string {
  return ESPN_ABBR_TO_TRICODE[abbr] ?? abbr;
}

export function normalizeName(name: string): string {
  const nfkd = name.normalize("NFKD");
  const stripped = nfkd.replace(/[̀-ͯ]/g, "");
  const lower = stripped.toLowerCase().replace(/[^a-z0-9 ]/g, "");
  const noSuffix = lower.replace(/\b(jr|sr|ii|iii|iv)\b/g, " ");
  return noSuffix.replace(/\s+/g, " ").trim();
}

export function matchPlayerId(
  name: string,
  candidates: { id: number; name: string }[],
): number | null {
  const targetNorm = normalizeName(name);
  for (const p of candidates) {
    const candNorm = normalizeName(p.name);
    if (candNorm === targetNorm) return p.id;
    const targetParts = targetNorm.split(" ").filter(Boolean);
    const candParts = candNorm.split(" ").filter(Boolean);
    const targetLast = targetParts[targetParts.length - 1] ?? "";
    const candLast = candParts[candParts.length - 1] ?? "";
    if (targetLast && targetLast === candLast) {
      if (targetParts.length >= 2 && candParts.length >= 2) {
        if (targetParts[0] === candParts[0]) return p.id;
      } else {
        return p.id;
      }
    }
  }
  return null;
}

type EspnBoxRow = {
  team: string;
  name: string;
  starter: boolean;
  played: boolean;
  minutes: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
  tov: number;
  fouls: number;
};

function splitMadeAttempted(s: string | undefined): [number, number] {
  if (!s) return [0, 0];
  const m = s.match(/^(\d+)-(\d+)$/);
  if (!m) return [0, 0];
  return [parseInt(m[1], 10), parseInt(m[2], 10)];
}

function numOr0(s: string | undefined): number {
  const n = s === undefined ? NaN : parseFloat(s);
  return Number.isFinite(n) ? n : 0;
}

export function parseEspnBox(summary: unknown): EspnBoxRow[] {
  const rows: EspnBoxRow[] = [];
  const players = (summary as { boxscore?: { players?: unknown[] } } | null)?.boxscore
    ?.players;
  if (!Array.isArray(players)) return rows;

  for (const teamEntry of players) {
    const team = teamEntry as {
      team?: { abbreviation?: string };
      statistics?: { labels?: string[]; athletes?: unknown[] }[];
    };
    const abbr = team.team?.abbreviation ?? "";
    const tricode = espnTricode(abbr);
    const stats = team.statistics?.[0];
    const labels = stats?.labels ?? [];
    const athletes = stats?.athletes ?? [];

    for (const a of athletes) {
      const athlete = a as {
        athlete?: { displayName?: string };
        starter?: boolean;
        didNotPlay?: boolean;
        stats?: string[];
      };
      const name = athlete.athlete?.displayName ?? "";
      const starter = athlete.starter ?? false;
      const statValues = athlete.stats ?? [];
      const byLabel: Record<string, string> = {};
      labels.forEach((label, i) => {
        byLabel[label] = statValues[i];
      });

      const played = statValues.length > 0 && !athlete.didNotPlay;
      const [fgm, fga] = splitMadeAttempted(byLabel["FG"]);
      const [tpm, tpa] = splitMadeAttempted(byLabel["3PT"]);
      const [ftm, fta] = splitMadeAttempted(byLabel["FT"]);

      rows.push({
        team: tricode,
        name,
        starter,
        played,
        minutes: played ? numOr0(byLabel["MIN"]) : 0,
        pts: played ? numOr0(byLabel["PTS"]) : 0,
        reb: played ? numOr0(byLabel["REB"]) : 0,
        ast: played ? numOr0(byLabel["AST"]) : 0,
        stl: played ? numOr0(byLabel["STL"]) : 0,
        blk: played ? numOr0(byLabel["BLK"]) : 0,
        fgm: played ? fgm : 0,
        fga: played ? fga : 0,
        tpm: played ? tpm : 0,
        tpa: played ? tpa : 0,
        ftm: played ? ftm : 0,
        fta: played ? fta : 0,
        tov: played ? numOr0(byLabel["TO"]) : 0,
        fouls: played ? numOr0(byLabel["PF"]) : 0,
      });
    }
  }

  return rows;
}

export type EspnEvent = {
  id: string;
  state: string;
  period: number;
  clock: string;
  homeScore: number;
  awayScore: number;
};

export function findEspnEvent(
  scoreboard: unknown,
  home: string,
  away: string,
): EspnEvent | null {
  const events = (scoreboard as { events?: unknown[] } | null)?.events;
  if (!Array.isArray(events)) return null;

  for (const ev of events) {
    const event = ev as {
      id?: string;
      status?: {
        period?: number;
        displayClock?: string;
        type?: { state?: string };
      };
      competitions?: {
        competitors?: {
          homeAway?: string;
          team?: { abbreviation?: string };
          score?: string;
        }[];
      }[];
    };
    const competitors = event.competitions?.[0]?.competitors ?? [];
    const homeC = competitors.find((c) => c.homeAway === "home");
    const awayC = competitors.find((c) => c.homeAway === "away");
    if (!homeC || !awayC) continue;

    const homeTricode = espnTricode(homeC.team?.abbreviation ?? "");
    const awayTricode = espnTricode(awayC.team?.abbreviation ?? "");
    if (homeTricode === home && awayTricode === away) {
      return {
        id: event.id ?? "",
        state: event.status?.type?.state ?? "",
        period: event.status?.period ?? 0,
        clock: event.status?.displayClock ?? "",
        homeScore: numOr0(homeC.score),
        awayScore: numOr0(awayC.score),
      };
    }
  }

  return null;
}

const SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard";
const SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary";

export async function fetchEspnLiveBox(
  date: string,
  home: string,
  away: string,
): Promise<{ event: EspnEvent; rows: EspnBoxRow[] } | null> {
  const scoreboardRes = await fetch(`${SCOREBOARD_URL}?dates=${date}`, {
    next: { revalidate: 8 },
  });
  if (!scoreboardRes.ok) return null;
  const scoreboard = await scoreboardRes.json();

  const event = findEspnEvent(scoreboard, home, away);
  if (!event) return null;

  const summaryRes = await fetch(`${SUMMARY_URL}?event=${event.id}`, {
    next: { revalidate: 8 },
  });
  if (!summaryRes.ok) return null;
  const summary = await summaryRes.json();
  const rows = parseEspnBox(summary);

  return { event, rows };
}
