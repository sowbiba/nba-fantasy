import Link from "next/link";

export default function PronoNotFound() {
  return (
    <div className="px-4 pt-10 pb-10 text-center animate-fade-in">
      <p className="text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
        Pronos NBA 2026-27
      </p>
      <h1 className="font-display text-4xl mt-2">Prono introuvable</h1>
      <p className="mt-2 text-sm text-[color:var(--color-text-mute)]">Ce lien ne correspond à aucun prono.</p>
      <Link
        href="/pronos-26-27"
        className="inline-block mt-6 text-xs uppercase tracking-[0.2em] text-[color:var(--color-text-soft)] underline underline-offset-4"
      >
        Voir tous les pronos
      </Link>
    </div>
  );
}
