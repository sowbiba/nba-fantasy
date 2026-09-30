"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LEAGUE_EXPECTED_WINS,
  TEAMS,
  leagueWinsTotal,
  standingsFromWins,
  type Conference,
  type WinsMap,
} from "@/lib/pronos";
import { createAutosave, type AutosaveState } from "@/lib/autosave";
import { shareFilename, sharePronoImage } from "@/lib/share";
import { saveProno } from "./actions";
import { useStoredToken } from "./token-store";
import PronoStandings from "./PronoStandings";

const CONFERENCES: Conference[] = ["Est", "Ouest"];
const STEPPER_BASE = 41; // premier appui sur −/+ d'une équipe vide : part de 41 (bilan à l'équilibre)

function clampWins(n: number): number {
  return Math.max(0, Math.min(82, Math.round(n)));
}

function withTeam(wins: WinsMap, team: string, value: number | null): WinsMap {
  const next = { ...wins };
  if (value === null) delete next[team];
  else next[team] = clampWins(value);
  return next;
}

type SavePayload = { token: string; wins: WinsMap };

export default function PronoEditor({
  id,
  name,
  initialWins,
  closed,
}: {
  id: string;
  name: string;
  initialWins: WinsMap;
  closed: boolean;
}) {
  const token = useStoredToken(id);
  // État local = source de vérité après le montage : chaque enregistrement
  // revalide la page serveur (nouveau `initialWins`), qu'on ignore
  // volontairement pour ne jamais écraser une saisie en cours.
  const [wins, setWins] = useState<WinsMap>(initialWins);
  const [saveState, setSaveState] = useState<AutosaveState | null>(null);
  const [closedNow, setClosedNow] = useState(false);
  const [autosave] = useState(() =>
    createAutosave<SavePayload>({
      save: (p) => saveProno(id, p.token, p.wins),
      onState: (s) => {
        setSaveState(s);
        if (s.status === "error" && s.error && /clos/i.test(s.error)) setClosedNow(true);
      },
    }),
  );

  const isClosed = closed || closedNow;
  const editable = !isClosed && token !== null;

  // Ne jamais perdre la dernière saisie : envoi immédiat quand l'onglet est
  // masqué/fermé ou que l'on quitte la page.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") autosave.flush();
    };
    const onPageHide = () => autosave.flush();
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onPageHide);
      autosave.flush();
    };
  }, [autosave]);

  function update(next: WinsMap) {
    if (!editable || token === null) return;
    setWins(next);
    autosave.schedule({ token, wins: next });
  }

  const standings = standingsFromWins(wins);
  const total = leagueWinsTotal(wins);
  const filled = Object.keys(wins).length;
  const offTarget = total !== LEAGUE_EXPECTED_WINS;

  function onShare() {
    autosave.flush();
    void sharePronoImage({
      imageUrl: `/pronos-26-27/${id}/image`,
      title: `Prono NBA 2026-27 de ${name}`,
      filename: shareFilename(name),
      nav: typeof navigator !== "undefined" ? navigator : undefined,
      fetchImpl: (url, init) => fetch(url, init),
      openUrl: (url) => {
        window.open(url, "_blank", "noopener");
      },
    });
  }

  return (
    <div className="px-4 pt-5 pb-10 animate-fade-in">
      <Link
        href="/pronos-26-27"
        className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)] underline underline-offset-4"
      >
        ← Tous les pronos
      </Link>
      <p className="mt-4 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
        Pronos NBA 2026-27
      </p>
      <h1 className="font-display text-5xl leading-none mt-1 break-words">{name}</h1>

      <div className="mt-3 min-h-5 text-xs">
        {isClosed ? (
          <p className="text-[color:var(--color-text-soft)]">Les pronos sont clos : lecture seule.</p>
        ) : token === null ? (
          <p className="text-[color:var(--color-text-soft)]">Ce prono appartient à {name}.</p>
        ) : (
          <SaveIndicator state={saveState} />
        )}
      </div>

      <div
        className="sticky z-10 mt-4 -mx-4 px-4 py-2.5 flex items-center justify-between gap-3 bg-[color:var(--color-ink)]/90 backdrop-blur border-y border-[color:var(--color-line-soft)]"
        style={{ top: "env(safe-area-inset-top, 0px)" }}
      >
        <div className="font-mono-num text-xs leading-tight">
          <div className={offTarget ? "text-[color:var(--color-gold)]" : "text-[color:var(--color-text)]"}>
            {total} / {LEAGUE_EXPECTED_WINS.toLocaleString("fr-FR")} victoires
          </div>
          <div className="text-[10px] text-[color:var(--color-text-mute)]">
            {filled}/30 équipes
            {offTarget && filled === 30 ? ` · écart ${total > LEAGUE_EXPECTED_WINS ? "+" : ""}${total - LEAGUE_EXPECTED_WINS}` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={onShare}
          className="h-9 px-4 rounded-full border border-[color:var(--color-line)] text-xs font-semibold text-[color:var(--color-text)] active:bg-white/5"
        >
          Partager
        </button>
      </div>
      {offTarget && filled === 30 && (
        <p className="mt-2 text-[11px] text-[color:var(--color-text-mute)]">
          Sur une saison, la ligue totalise {LEAGUE_EXPECTED_WINS.toLocaleString("fr-FR")} victoires : ton total
          s&apos;en écarte (simple info, rien n&apos;est bloqué).
        </p>
      )}

      <div className="mt-6 flex flex-col gap-10">
        {CONFERENCES.map((conf) => (
          <section key={conf} aria-labelledby={`conf-${conf}`} className="flex flex-col gap-5">
            <h2 id={`conf-${conf}`} className="font-display text-3xl leading-none">
              Conférence {conf}
            </h2>
            {editable && (
              <div className="surface-flat px-3 py-1 divide-y divide-white/[0.04]">
                {TEAMS.filter((t) => t.conference === conf).map((t) => (
                  <TeamInput
                    key={t.code}
                    team={t.code}
                    value={wins[t.code]}
                    onChange={(v) => update(withTeam(wins, t.code, v))}
                  />
                ))}
              </div>
            )}
            <PronoStandings conference={conf} rows={standings[conf]} />
          </section>
        ))}
        <p className="text-[10px] text-[color:var(--color-text-mute)] tracking-wide">1-6 playoffs · 7-10 play-in</p>
      </div>
    </div>
  );
}

function SaveIndicator({ state }: { state: AutosaveState | null }) {
  if (!state) {
    return <p className="text-[color:var(--color-text-mute)]">Ton prono · enregistrement automatique</p>;
  }
  if (state.status === "error") {
    return (
      <p role="alert" className="text-[color:var(--color-crimson)]">
        {state.error}
      </p>
    );
  }
  if (state.status === "saved") {
    return (
      <p aria-live="polite">
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-[color:var(--color-emerald)]/30 text-[color:var(--color-emerald)] text-[10px] uppercase tracking-[0.18em]">
          Enregistré
        </span>
      </p>
    );
  }
  return (
    <p aria-live="polite" className="text-[color:var(--color-text-mute)]">
      Enregistrement…
    </p>
  );
}

function TeamInput({
  team,
  value,
  onChange,
}: {
  team: string;
  value: number | undefined;
  onChange: (v: number | null) => void;
}) {
  const base = value ?? STEPPER_BASE;
  const stepBtn =
    "w-10 h-10 shrink-0 rounded-full border border-[color:var(--color-line)] text-lg leading-none text-[color:var(--color-text)] active:bg-white/10 disabled:opacity-30";
  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="w-11 font-bold text-sm text-white">{team}</span>
      <button
        type="button"
        aria-label={`Une victoire de moins pour ${team}`}
        className={stepBtn}
        disabled={value === 0}
        onClick={() => onChange(value === undefined ? STEPPER_BASE : base - 1)}
      >
        −
      </button>
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={2}
        aria-label={`Victoires ${team}`}
        placeholder="—"
        value={value === undefined ? "" : String(value)}
        onChange={(e) => {
          const digits = e.target.value.replace(/\D/g, "");
          onChange(digits === "" ? null : Number(digits));
        }}
        className="w-14 h-10 shrink-0 text-center font-mono-num text-base rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)] placeholder:text-[color:var(--color-text-dim)] focus:outline-none focus:border-[color:var(--color-flame)]"
      />
      <button
        type="button"
        aria-label={`Une victoire de plus pour ${team}`}
        className={stepBtn}
        disabled={value === 82}
        onClick={() => onChange(value === undefined ? STEPPER_BASE : base + 1)}
      >
        +
      </button>
      <span className="ml-auto font-mono-num text-xs text-[color:var(--color-text-mute)]">
        {value === undefined ? "—" : `${value}-${82 - value}`}
      </span>
    </div>
  );
}
