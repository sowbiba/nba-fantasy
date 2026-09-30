import type { Metadata } from "next";
import Link from "next/link";
import { getClosure, listPronosCore } from "./core";
import { parisDateTime } from "@/lib/date";
import CreatePronoForm from "./CreatePronoForm";
import OwnedBadge from "./OwnedBadge";

// Page autonome (sans habillage, cf. STANDALONE_PREFIXES), non liée depuis
// l'application et non indexée. Toujours dynamique : jamais d'instantané de
// la liste au build.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Pronos NBA 2026-27",
  description: "Bilans de la saison régulière 2026-27, équipe par équipe.",
  robots: { index: false, follow: false },
};

export default async function PronosHome() {
  const [pronos, closure] = await Promise.all([listPronosCore(), getClosure()]);

  return (
    <div className="px-4 pt-6 pb-10 animate-fade-in">
      <p className="text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
        Pronos NBA 2026-27
      </p>
      <h1 className="font-display text-5xl leading-none mt-1">Bilans de la saison</h1>
      <p className="mt-3 text-sm text-[color:var(--color-text-soft)]">
        Devine le nombre de victoires de chaque équipe en saison régulière (sur 82 matchs).
      </p>
      <p className="mt-1 text-xs text-[color:var(--color-text-mute)]">
        {closure.closed
          ? `Clôture le ${parisDateTime(closure.deadline)}.`
          : `Modifiable jusqu'au premier match : ${parisDateTime(closure.deadline)}.`}
      </p>

      <div className="mt-6">
        {closure.closed ? (
          <div className="surface p-5 text-center">
            <div className="font-display text-2xl">Les pronos sont clos</div>
            <p className="mt-1 text-xs text-[color:var(--color-text-mute)]">La saison a commencé.</p>
          </div>
        ) : (
          <CreatePronoForm />
        )}
      </div>

      <section className="mt-8" aria-labelledby="pronostiqueurs">
        <h2
          id="pronostiqueurs"
          className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2"
        >
          Les pronostiqueurs ({pronos.length})
        </h2>
        {pronos.length === 0 ? (
          <div className="surface-flat p-5 text-center text-sm text-[color:var(--color-text-mute)]">
            Aucun prono pour l&apos;instant.
          </div>
        ) : (
          <ul className="surface-flat divide-y divide-white/[0.04]">
            {pronos.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/pronos-26-27/${p.id}`}
                  className="flex items-center gap-3 px-4 py-3 active:bg-white/5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-[color:var(--color-text)] truncate">{p.name}</div>
                    <div className="text-[11px] text-[color:var(--color-text-mute)]">
                      Mis à jour le {parisDateTime(p.updatedAt)}
                    </div>
                  </div>
                  <OwnedBadge id={p.id} />
                  <span aria-hidden className="text-[color:var(--color-text-mute)]">
                    →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
