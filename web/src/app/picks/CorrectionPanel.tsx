"use client";

import { useEffect, useState, useTransition } from "react";
import { correctPick, playersForNight } from "@/app/actions";

type Player = { id: number; name: string; team: string };

function normalize(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** Panneau de correction d'une soirée passée (synchro TrashTalk oubliée) :
 *  remplacer, ajouter ou supprimer le pick de cette soirée. */
export default function CorrectionPanel({
  date, currentPlayerId, onDone,
}: { date: string; currentPlayerId: number | null; onDone: () => void }) {
  const [players, setPlayers] = useState<Player[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
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

  const pick = (playerId: number | null) => {
    setError(null);
    startTransition(async () => {
      const res = await correctPick({ date, playerId });
      if (!res.ok) { setError(res.error); return; }
      onDone();
    });
  };

  const deleteClick = () => {
    if (!confirmingDelete) { setConfirmingDelete(true); return; }
    pick(null);
  };

  const filtered = (players ?? [])
    .filter((p) => p.id !== currentPlayerId)
    .filter((p) => normalize(p.name).includes(normalize(query)));

  return (
    <div className="mt-1 rounded-[var(--radius-card-sm)] border border-white/10 bg-black/20 p-2">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Chercher un joueur…"
        disabled={pending}
        className="w-full rounded-md bg-[color:var(--color-surface)] border border-white/10 px-2 py-1 text-xs text-[color:var(--color-text)] placeholder:text-[color:var(--color-text-mute)] disabled:opacity-50"
      />
      <ul className="mt-1.5 max-h-40 overflow-y-auto flex flex-col gap-0.5">
        {players === null && <li className="text-[11px] text-[color:var(--color-text-mute)] px-1 py-1">Chargement…</li>}
        {players !== null && filtered.length === 0 && (
          <li className="text-[11px] text-[color:var(--color-text-mute)] px-1 py-1">Aucun joueur trouvé.</li>
        )}
        {filtered.map((p) => (
          <li key={p.id}>
            <button onClick={() => pick(p.id)} disabled={pending}
                    className="w-full text-left px-2 py-1 rounded-md text-xs text-[color:var(--color-text)] hover:bg-white/5 disabled:opacity-50">
              {p.name} <span className="text-[10px] text-[color:var(--color-text-mute)]">{p.team}</span>
            </button>
          </li>
        ))}
      </ul>
      {currentPlayerId !== null && (
        <button onClick={deleteClick} disabled={pending}
                className="mt-1.5 text-[10px] underline text-[color:var(--color-crimson)] disabled:opacity-50">
          {confirmingDelete ? "Confirmer : la soirée comptera 0" : "Supprimer ce pick"}
        </button>
      )}
      {error && <p role="alert" className="mt-1.5 text-[11px] text-[color:var(--color-crimson)]">{error}</p>}
    </div>
  );
}
