"use client";

import { useState, useTransition } from "react";
import { correctX2, setX2 } from "@/app/actions";

/** Déclarer (ou retirer) le x2 posé sur un pick. `correction` : soirée
 *  passée, la fermeture est levée en base (correct_x2) ; sinon setX2,
 *  refusé une fois la soirée fermée. Unicité mensuelle et fenêtre
 *  novembre-avril : vérifiées par la base, l'erreur s'affiche ici. */
export default function X2Toggle({ date, isX2, correction = false }: { date: string; isX2: boolean; correction?: boolean }) {
  const [x2, setLocalX2] = useState(isX2);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const toggle = () => {
    setError(null);
    startTransition(async () => {
      const res = await (correction ? correctX2 : setX2)({ date, value: !x2 });
      if (res.ok) setLocalX2(!x2);
      else setError(res.error);
    });
  };

  return (
    <span className="inline-flex flex-col items-start">
      <button onClick={toggle} disabled={pending}
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold border disabled:opacity-50 ${x2
                ? "bg-[color:var(--color-gold)] text-black border-[color:var(--color-gold)]"
                : "border-white/15 text-[color:var(--color-text-soft)]"}`}>
        {pending ? "…" : x2 ? "x2 ACTIVÉ" : "ACTIVER x2"}
      </button>
      {error && <span role="alert" className="mt-1 text-[11px] text-[color:var(--color-crimson)]">{error}</span>}
    </span>
  );
}
