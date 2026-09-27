"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import SignOutButton from "@/components/SignOutButton";

/** Ligne « Mode connecté » / « Déconnexion », dans le flux (plus en
 *  `fixed`) pour ne plus recouvrir les onglets/boutons du haut de page
 *  (/games, /games/classement, /picks). Masquée sur /connexion (M4) : la
 *  page a déjà son propre lien/état, inutile de la dupliquer ici. */
export default function HeaderControl({ owner }: { owner: boolean }) {
  const pathname = usePathname();
  if (pathname === "/connexion") return null;

  return (
    <div className="max-w-lg mx-auto flex justify-end px-4 pt-2">
      {owner ? (
        <SignOutButton />
      ) : (
        <Link
          href="/connexion"
          className="text-[11px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)] underline"
        >
          Mode connecté
        </Link>
      )}
    </div>
  );
}
