"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { savePick } from "@/app/actions";
import { addDays, frLongDate, parisTime } from "@/lib/date";
import { HARD_OUT_STATUSES, isClosed, x2AllowedOn } from "@/lib/display";
import NightPlayerPicker from "./NightPlayerPicker";
import X2Toggle from "./X2Toggle";

export type DeckNightProps = {
  date: string; closingAt: string; nGames: number; isPhantom: boolean; isToday: boolean; mode: "regular" | "playoffs";
  pick: { playerId: number; name: string; team: string; injury: string | null; injuryReturn?: string | null;
          /** Dernier statut daté, conservé après le retour : période de sécurité de 7 jours. */
          lastInjury?: { status: string; seen: string } | null; isX2: boolean } | null;
  /** Joueur du plan. Si la soirée est déjà pickée avec un autre joueur, le
   *  plan conteste la réservation ; `reservedOn` = autre soirée où ce joueur
   *  est déjà réservé (il faut alors échanger, pas remplacer en un clic). */
  suggestion: { playerId: number; name: string; team: string; gameId: string; projection: number; explanation: string; isX2: boolean; reservedOn?: string | null } | null;
};

export default function DeckNight(p: DeckNightProps) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [choosing, setChoosing] = useState(false);
  const closed = isClosed(p.closingAt);

  const reserve = () => {
    if (!p.suggestion) return;
    const s = p.suggestion;
    setMsg(null);
    startTransition(async () => {
      const res = await savePick({ date: p.date, playerId: s.playerId, gameId: s.gameId });
      setMsg(res.ok ? "Réservé. Pense à le reporter sur trashtalk.co." : res.error);
    });
  };
  const challenger = p.pick && p.suggestion && p.suggestion.playerId !== p.pick.playerId ? p.suggestion : null;

  return (
    <div className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-3 py-2.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-[color:var(--color-text)] capitalize">
          {p.isToday ? "Ce soir" : frLongDate(p.date)}
        </span>
        <span className="text-[10px] text-[color:var(--color-text-mute)]">
          {p.nGames} match{p.nGames > 1 ? "s" : ""} · fermeture {parisTime(p.closingAt)}
        </span>
      </div>
      {p.isPhantom && (
        <p className="mt-1 text-xs text-[color:var(--color-crimson)]">Soirée fantôme : aucun match réel, déplace ta réservation.</p>
      )}
      {p.pick ? (
        <div className="mt-1 text-sm">
          <Link href={`/player/${p.pick.playerId}`} className="font-semibold text-[color:var(--color-emerald)]">
            {p.pick.name}
          </Link>{" "}
          <span className="text-[11px] text-[color:var(--color-text-mute)]">
            {p.pick.team}{p.pick.isX2 && (closed || !x2AllowedOn(p.date, p.mode)) ? " · x2" : ""}
            {p.suggestion?.isX2 && !p.pick.isX2 && p.suggestion.playerId === p.pick.playerId ? " · plan : x2 ce soir-là" : ""}
          </span>
          {!closed && x2AllowedOn(p.date, p.mode) && (
            <span className="ml-1 align-middle"><X2Toggle key={`${p.pick.playerId}:${p.pick.isX2}`} date={p.date} isX2={p.pick.isX2} /></span>
          )}
          {p.pick.injury && HARD_OUT_STATUSES.has(p.pick.injury) && !closed && (
            <p className="text-xs text-[color:var(--color-crimson)]">⚠️ {p.pick.injury} : remplace-le avant la fermeture.</p>
          )}
          {p.pick.injury && !HARD_OUT_STATUSES.has(p.pick.injury) && !closed && (
            <p className="text-xs text-[color:var(--color-gold)]">
              ⚠️ {p.pick.injury}{p.pick.injuryReturn && /^\d{4}-\d{2}-\d{2}/.test(p.pick.injuryReturn) ? ` · retour estimé ${frLongDate(p.pick.injuryReturn.slice(0, 10))}` : ""} : à surveiller.
            </p>
          )}
          {!p.pick.injury && p.pick.lastInjury && p.date < addDays(p.pick.lastInjury.seen, 7) && !closed && (
            <p className="text-xs text-[color:var(--color-gold)]">
              ⚠️ Retour de blessure ({p.pick.lastInjury.status} jusqu&apos;au {frLongDate(p.pick.lastInjury.seen)}) : période de sécurité de 7 jours.
            </p>
          )}
          {challenger && !closed && (
            <div className="mt-1 flex items-center justify-between gap-3 rounded-[var(--radius-card-sm)] border border-[color:var(--color-gold)]/30 px-2 py-1.5">
              <p className="min-w-0 text-xs text-[color:var(--color-text-soft)]">
                Le moteur préfère{" "}
                <Link href={`/player/${challenger.playerId}`} className="font-semibold text-[color:var(--color-text)]">{challenger.name}</Link>{" "}
                <span className="text-[11px] text-[color:var(--color-text-mute)]">
                  {challenger.explanation}
                  {challenger.reservedOn ? ` · déjà réservé ${frLongDate(challenger.reservedOn)} : échange les deux soirées` : " · indicatif"}
                </span>
              </p>
              {!challenger.reservedOn && (
                <button onClick={reserve} disabled={pending}
                        className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
                  REMPLACER
                </button>
              )}
            </div>
          )}
        </div>
      ) : p.suggestion ? (
        <div className="mt-1 flex items-center justify-between gap-3">
          <div className="min-w-0 text-sm">
            <Link href={`/player/${p.suggestion.playerId}`} className="text-[color:var(--color-text)]">
              {p.suggestion.name}
            </Link>{" "}
            {p.suggestion.isX2 && (
              <span title="Le plan suggère le x2 cette nuit-là" className="rounded-full bg-[color:var(--color-gold)]/15 border border-[color:var(--color-gold)]/40 px-1.5 py-0.5 text-[10px] font-bold text-[color:var(--color-gold)]">
                x2
              </span>
            )}{" "}
            <span className="text-[11px] text-[color:var(--color-text-mute)]">{p.suggestion.explanation}</span>
          </div>
          {closed ? (
            <span className="shrink-0 text-[11px] text-[color:var(--color-text-mute)]">Fermé</span>
          ) : (
            <button onClick={reserve} disabled={pending}
                    className="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold text-white bg-[color:var(--color-flame)] disabled:opacity-50">
              RÉSERVER
            </button>
          )}
        </div>
      ) : (
        <p className="mt-1 text-xs text-[color:var(--color-text-mute)]">Pas encore de suggestion.</p>
      )}
      {!closed && (
        <button onClick={() => { setMsg(null); setChoosing((c) => !c); }}
                className="mt-1 text-[11px] underline text-[color:var(--color-text-mute)]">
          {choosing ? "Annuler" : p.pick ? "Changer de joueur" : "Autre joueur"}
        </button>
      )}
      {choosing && !closed && (
        <NightPlayerPicker date={p.date} current={p.pick ? { playerId: p.pick.playerId, name: p.pick.name } : null}
          onDone={(name) => { setChoosing(false); setMsg(`${name} réservé. Pense à le reporter sur trashtalk.co.`); }} />
      )}
      {msg && <p role="alert" className="mt-1 text-xs text-[color:var(--color-text-soft)]">{msg}</p>}
    </div>
  );
}
