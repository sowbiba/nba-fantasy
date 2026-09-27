import Link from "next/link";

/** Onglets Matchs · Classement, en haut de la section Matchs (les deux
 *  modes). Composant serveur : deux routes (`/games`, `/games/classement`),
 *  pas d'état client nécessaire. */
export default function GamesTabs({ active }: { active: "matchs" | "classement" }) {
  const tabClass = (isActive: boolean) =>
    `flex-1 text-center py-2 rounded-[var(--radius-card-sm)] text-xs font-bold uppercase tracking-[0.14em] transition-colors ${
      isActive
        ? "bg-[color:var(--color-flame)]/15 text-[color:var(--color-flame)] border border-[color:var(--color-flame)]/30"
        : "text-[color:var(--color-text-mute)] border border-white/5"
    }`;

  return (
    <div className="flex gap-2 mb-4" role="tablist" aria-label="Matchs ou classement">
      <Link href="/games" role="tab" aria-selected={active === "matchs"} className={tabClass(active === "matchs")}>
        Matchs
      </Link>
      <Link href="/games/classement" role="tab" aria-selected={active === "classement"} className={tabClass(active === "classement")}>
        Classement
      </Link>
    </div>
  );
}
