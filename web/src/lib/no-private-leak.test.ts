import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// Test anti-fuite (tâche 4) : aucun fichier de web/src ne doit lire une
// donnée TTFL privée (migration 028) avec le client anon public `supabase`
// (import "@/lib/supabase/public"). Les seuls fichiers autorisés à utiliser
// le client service (après vérification de la session) sont exclus car ils
// n'utilisent jamais le client public pour ces tables/fonctions :
// lib/viewer.ts (définit ownerDb), app/actions.ts et app/api/reminders/**
// (déjà des actions serveur protégées par requireOwner()).
const SRC_DIR = fileURLToPath(new URL("..", import.meta.url));

const EXCLUDED = [join(SRC_DIR, "lib", "viewer.ts"), join(SRC_DIR, "app", "actions.ts")];
const EXCLUDED_DIRS = [join(SRC_DIR, "app", "api", "reminders")];

const PRIVATE_TABLES = [
  "picks",
  "recommendations",
  "plan_latest",
  "player_watchlist",
  "second_chances",
  "team_elo",
  "game_predictions",
  "season_pronos",
];
const PRIVATE_RPCS = ["period_stats", "player_calendar"];

// `\s*` (qui matche aussi les retours à la ligne) entre `supabase`, `.` et
// `from(`/`rpc(` : le style du dépôt écrit parfois l'appel sur plusieurs
// lignes (`supabase\n  .from("recommendations")`), un simple grep sur une
// seule ligne le raterait.
const LEAK_PATTERNS = [
  ...PRIVATE_TABLES.map((t) => new RegExp(`supabase\\s*\\.\\s*from\\s*\\(\\s*["']${t}["']`)),
  ...PRIVATE_RPCS.map((f) => new RegExp(`supabase\\s*\\.\\s*rpc\\s*\\(\\s*["']${f}["']`)),
];

function findLeaks(content: string): RegExp[] {
  return LEAK_PATTERNS.filter((pattern) => pattern.test(content));
}

function isExcluded(path: string): boolean {
  if (EXCLUDED.includes(path)) return true;
  return EXCLUDED_DIRS.some((dir) => path === dir || path.startsWith(dir + "/"));
}

function walk(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      files.push(...walk(full));
    } else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith(".test.ts") && !entry.endsWith(".test.tsx")) {
      files.push(full);
    }
  }
  return files;
}

describe("findLeaks (détecteur du test anti-fuite)", () => {
  it("détecte un appel sur une seule ligne", () => {
    expect(findLeaks('supabase.from("picks").select("*")')).not.toEqual([]);
    expect(findLeaks('supabase.from("team_elo").select("*")')).not.toEqual([]);
    expect(findLeaks('supabase.rpc("period_stats", {})')).not.toEqual([]);
  });

  it("détecte un appel écrit sur plusieurs lignes (style chaîné du dépôt)", () => {
    expect(findLeaks('supabase\n  .from("recommendations")\n  .select("*")')).not.toEqual([]);
    expect(findLeaks('supabase\n  .rpc("player_calendar", {\n    p_player_id: 1,\n  })')).not.toEqual([]);
  });

  it("ignore le client service et les tables/fonctions publiques", () => {
    expect(findLeaks('db.from("picks").select("*")')).toEqual([]);
    expect(findLeaks('supabase.from("nights").select("*")')).toEqual([]);
    expect(findLeaks('supabase.from("games").select("*")')).toEqual([]);
    expect(findLeaks('supabase.rpc("some_public_fn", {})')).toEqual([]);
  });
});

describe("anti-fuite : données TTFL privées jamais lues avec le client public", () => {
  const files = walk(SRC_DIR).filter((f) => !isExcluded(f));

  it("ne contient aucun appel supabase.from/rpc sur une table ou fonction privée", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      for (const pattern of findLeaks(content)) {
        offenders.push(`${relative(SRC_DIR, file)} — ${pattern}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("a bien parcouru des fichiers (le test ne passe pas par défaut faute de contenu)", () => {
    expect(files.length).toBeGreaterThan(10);
  });
});
