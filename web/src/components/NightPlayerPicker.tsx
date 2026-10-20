"use client";

import { useEffect, useState, useTransition } from "react";
import { playersForNight, savePick } from "@/app/actions";

type Player = { id: number; name: string; team: string; gameId: string };

function normalize(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** Réserver un autre joueur que la suggestion pour une soirée du Deck (picks
 *  faits à la semaine). Les règles (cooldown, R9, fermeture) restent
 *  vérifiées par savePick et le trigger picks_validate. */
export default function NightPlayerPicker({
  date, current, onDone,
}: { date: string; current: { playerId: number; name: string } | null; onDone: (name: string) => void }) {
  const [players, setPlayers] = useState<Player[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    playersForNight(date)
      .then((data) => { if (!cancelled) setPlayers(data); })
      .catch(() => {
        if (cancelled) return;
        setPlayers([]);
        setError("Impossible de charger les joueurs, réessaie dans quelques minutes.");
      });
    return () => { cancelled = true; };
  }, [date]);

  const choose = (p: Player) => {
    // Remplacer un pick existant demande une confirmation (comme PickControls).
    if (current && confirmingId !== p.id) { setConfirmingId(p.id); return; }
    setError(null);
    startTransition(async () => {
      const res = await savePick({ date, playerId: p.id, gameId: p.gameId });
      if (!res.ok) { setError(res.error); setConfirmingId(null); return; }
      onDone(p.name);
    });
  };

  const filtered = (players ?? [])
    .filter((p) => p.id !== current?.playerId)
    .filter((p) => normalize(p.name).includes(normalize(query)));

  return (
    <div className="mt-1.5 rounded-[var(--radius-card-sm)] border border-white/10 bg-black/20 p-2">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Chercher un joueur…"
        disabled={pending}
        className="w-full rounded-md bg-[color:var(--color-surface)] border border-white/10 px-2 py-1 text-xs text-[color:var(--color-text)] placeholder:text-[color:var(--color-text-mute)] disabled:opacity-50"
      />
      <ul className="mt-1.5 max-h-48 overflow-y-auto flex flex-col gap-0.5">
        {players === null && <li className="text-[11px] text-[color:var(--color-text-mute)] px-1 py-1">Chargement…</li>}
        {players !== null && filtered.length === 0 && (
          <li className="text-[11px] text-[color:var(--color-text-mute)] px-1 py-1">Aucun joueur trouvé.</li>
        )}
        {filtered.map((p) => (
          <li key={p.id}>
            <button onClick={() => choose(p)} disabled={pending}
                    className="w-full text-left px-2 py-1 rounded-md text-xs text-[color:var(--color-text)] hover:bg-white/5 disabled:opacity-50">
              {confirmingId === p.id
                ? <span className="font-semibold text-[color:var(--color-flame)]">Confirmer : remplacer {current?.name} par {p.name}</span>
                : <>{p.name} <span className="text-[10px] text-[color:var(--color-text-mute)]">{p.team}</span></>}
            </button>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="mt-1.5 text-[11px] text-[color:var(--color-crimson)]">{error}</p>}
    </div>
  );
}
