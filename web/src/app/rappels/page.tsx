import { redirect } from "next/navigation";
import { getViewer } from "@/lib/viewer";
import PushControls from "./PushControls";

export const revalidate = 0;

export default async function RappelsPage() {
  const viewer = await getViewer();
  if (!viewer.owner) redirect("/");

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
        <PushControls />
      </div>
    </div>
  );
}
