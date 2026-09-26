import Link from "next/link";
import { createAuthClient } from "@/lib/supabase/server";
import { isOwnerEmail } from "@/lib/auth";
import PushControls from "./PushControls";

export const revalidate = 0;

export default async function RappelsPage() {
  const auth = await createAuthClient();
  const { data: userData } = await auth.auth.getUser();
  const signedIn = isOwnerEmail(userData.user?.email, process.env.OWNER_EMAIL);

  return (
    <div className="px-4 py-5 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        <span className="flame-text">RAPPELS</span>
      </h1>
      <p className="text-sm text-[color:var(--color-text-soft)] mt-3">
        Deux rappels par notification, si activés :
      </p>
      <ul className="text-sm text-[color:var(--color-text-soft)] mt-2 list-disc pl-5 space-y-1">
        <li>Oubli de pick : 2 h puis 30 min avant la fermeture de la soirée.</li>
        <li>Blessure ou indisponibilité annoncée pour le joueur pické.</li>
      </ul>

      <div className="mt-6">
        {signedIn ? (
          <PushControls />
        ) : (
          <p className="text-sm text-[color:var(--color-text-soft)]">
            <Link href="/connexion" className="underline">Connecte-toi</Link> pour activer les rappels.
          </p>
        )}
      </div>
    </div>
  );
}
