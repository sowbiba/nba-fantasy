"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  CLOSED_ERROR,
  LEAGUE_EXPECTED_WINS,
  TEAMS,
  isComplete,
  leagueWinsTotal,
  maxWinsFor,
  remainingWins,
  standingsFromWins,
  type Conference,
  type WinsMap,
} from "@/lib/pronos";
import { createAutosave, type AutosaveState } from "@/lib/autosave";
import { fetchShareFile, shareCachedFile, shareFilename, supportsFileShare } from "@/lib/share";
import { saveProno } from "./actions";
import { useStoredToken } from "./token-store";
import PronoStandings from "./PronoStandings";

const CONFERENCES: Conference[] = ["Est", "Ouest"];
const STEPPER_BASE = 41; // premier appui sur −/+ d'une équipe vide : part de 41 (bilan à l'équilibre)

// Borne une saisie à [0, max de l'équipe] : 82, et jamais au-delà des
// 1230 victoires de la ligue (le serveur refuse aussi tout dépassement).
function withTeam(wins: WinsMap, team: string, value: number | null): WinsMap {
  const next = { ...wins };
  if (value === null) delete next[team];
  else next[team] = Math.max(0, Math.min(maxWinsFor(wins, team), Math.round(value)));
  return next;
}

type SavePayload = { token: string; wins: WinsMap };

// Capacité statique du navigateur : partager un fichier png via Web Share.
// Lue via useSyncExternalStore (false au rendu serveur, puis la vraie valeur).
let fileShareSupport: boolean | null = null;
function readFileShareSupport(): boolean {
  if (fileShareSupport === null) {
    fileShareSupport = supportsFileShare(navigator, new File([], "prono.png", { type: "image/png" }));
  }
  return fileShareSupport;
}
const noSubscribe = () => () => {};

const shareBtn =
  "h-9 px-4 inline-flex items-center rounded-full border border-[color:var(--color-line)] text-xs font-semibold text-[color:var(--color-text)] active:bg-white/5";

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
  // Copie à jour pour les gestionnaires d'événements (jamais lue au rendu) :
  // chaque modification part de la dernière carte, pas de celle du rendu.
  const winsRef = useRef<WinsMap>(initialWins);
  const [saveState, setSaveState] = useState<AutosaveState | null>(null);
  const [closedNow, setClosedNow] = useState(false);
  const [showImageLink, setShowImageLink] = useState(false);
  const [autosave] = useState(() => {
    const a = createAutosave<SavePayload>({
      save: (p) => saveProno(id, p.token, p.wins),
      onState: (s) => {
        setSaveState(s);
        if (s.status === "error" && s.error === CLOSED_ERROR) {
          setClosedNow(true);
          a.cancel();
        }
      },
    });
    return a;
  });

  const imageUrl = `/pronos-26-27/${id}/image`;
  const shareTitle = `Prono NBA 2026-27 de ${name}`;
  const filename = shareFilename(name);
  const canFileShare = useSyncExternalStore(noSubscribe, readFileShareSupport, () => false);
  // Image pré-chargée pour un partage synchrone au clic (iOS exige
  // navigator.share sans await avant). `imageVersion` invalide le fichier à
  // chaque saisie : il n'est tenu pour frais qu'une fois l'état « Enregistré ».
  const shareFileRef = useRef<File | null>(null);
  const imageVersionRef = useRef(0);
  const saveStatus = saveState?.status ?? "idle";

  const isClosed = closed || closedNow;
  const editable = !isClosed && typeof token === "string";

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

  // Nouvel essai automatique au retour du réseau (après un échec réseau).
  useEffect(() => {
    const onOnline = () => autosave.flush();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [autosave]);

  // Pré-chargement de l'image de partage : seulement si le navigateur sait
  // partager un fichier (sinon on n'affiche qu'un lien, inutile de faire
  // rendre un png au serveur), au montage puis ~1 s après chaque
  // « Enregistré ». Jamais pendant une saisie en attente/en cours ni après
  // une erreur (l'image ne refléterait pas la saisie affichée).
  const complete = isComplete(wins);

  useEffect(() => {
    if (!canFileShare || !complete) return;
    if (saveStatus !== "idle" && saveStatus !== "saved") return;
    const version = imageVersionRef.current;
    const timer = setTimeout(
      () => {
        void fetchShareFile({ imageUrl, filename, fetchImpl: (url, init) => fetch(url, init) }).then((file) => {
          if (file && imageVersionRef.current === version) shareFileRef.current = file;
        });
      },
      saveStatus === "idle" ? 0 : 1000,
    );
    return () => clearTimeout(timer);
  }, [canFileShare, complete, saveStatus, imageUrl, filename]);

  function update(next: WinsMap) {
    if (!editable || typeof token !== "string") return;
    winsRef.current = next;
    imageVersionRef.current += 1;
    shareFileRef.current = null;
    setWins(next);
    autosave.schedule({ token, wins: next });
  }

  function setTeam(team: string, value: number | null) {
    update(withTeam(winsRef.current, team, value));
  }

  const standings = standingsFromWins(wins);
  const total = leagueWinsTotal(wins);
  const filled = Object.keys(wins).length;
  const remaining = remainingWins(wins);

  function onShare() {
    // PREMIÈRE instruction, sans await avant : navigator.share doit partir
    // pendant l'activation utilisateur du clic (iOS Safari).
    const attempt = shareCachedFile(navigator, shareFileRef.current, shareTitle);
    autosave.flush();
    if (attempt.kind === "link") {
      // Image pas encore prête (saisie en cours) : lien à cliquer, jamais de
      // window.open hors geste utilisateur (bloqué comme pop-up).
      setShowImageLink(true);
      return;
    }
    void attempt.done.then((outcome) => {
      if (outcome === "failed") setShowImageLink(true);
    });
  }

  const imageLink = (
    <a href={imageUrl} target="_blank" rel="noopener" className={shareBtn}>
      Ouvrir l&apos;image
    </a>
  );

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
        ) : token === undefined ? null : token === null ? (
          <p className="text-[color:var(--color-text-soft)]">Ce prono appartient à {name}.</p>
        ) : (
          <SaveIndicator state={saveState} onRetry={() => autosave.flush()} />
        )}
      </div>

      <div
        className="sticky z-10 mt-4 -mx-4 px-4 py-2.5 flex items-center justify-between gap-3 bg-[color:var(--color-ink)]/90 backdrop-blur border-y border-[color:var(--color-line-soft)]"
        style={{ top: "env(safe-area-inset-top, 0px)" }}
      >
        <div className="font-mono-num text-xs leading-tight">
          <div className={complete ? "text-[color:var(--color-text)]" : "text-[color:var(--color-gold)]"}>
            {total} / {LEAGUE_EXPECTED_WINS.toLocaleString("fr-FR")} victoires
          </div>
          <div className="text-[10px] text-[color:var(--color-text-mute)]">
            {filled}/30 équipes
            {remaining > 0 ? ` · ${remaining} à distribuer` : ""}
          </div>
        </div>
        {!complete ? (
          <span className="text-[10px] text-right leading-tight text-[color:var(--color-text-mute)] max-w-[9rem]">
            Image dispo une fois les 30 équipes saisies et les 1 230 victoires distribuées
          </span>
        ) : canFileShare ? (
          <div className="flex items-center gap-2">
            {showImageLink && imageLink}
            <button type="button" onClick={onShare} className={shareBtn}>
              Partager
            </button>
          </div>
        ) : (
          imageLink
        )}
      </div>
      {editable && remaining === 0 && !complete && (
        <p className="mt-2 text-[11px] text-[color:var(--color-text-mute)]">
          Les {LEAGUE_EXPECTED_WINS.toLocaleString("fr-FR")} victoires de la ligue sont toutes distribuées : baisse une
          équipe pour en donner à une autre.
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
                    max={maxWinsFor(wins, t.code)}
                    onChange={(v) => setTeam(t.code, v)}
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

function SaveIndicator({ state, onRetry }: { state: AutosaveState | null; onRetry: () => void }) {
  if (!state) {
    return <p className="text-[color:var(--color-text-mute)]">Ton prono · enregistrement automatique</p>;
  }
  if (state.status === "error") {
    return (
      <p role="alert" className="text-[color:var(--color-crimson)]">
        {state.error}
        {state.retryable && (
          <>
            {" "}
            <button type="button" onClick={onRetry} className="underline underline-offset-2 font-semibold">
              Réessayer
            </button>
          </>
        )}
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
  max,
  onChange,
}: {
  team: string;
  value: number | undefined;
  /** Plus haute valeur permise (82, ou moins si la ligue approche 1230). */
  max: number;
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
        disabled={value !== undefined ? value >= max : max === 0}
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
