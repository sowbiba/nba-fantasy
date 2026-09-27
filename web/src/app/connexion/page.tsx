import { redirect } from "next/navigation";
import { getViewer } from "@/lib/viewer";
import LoginForm from "./LoginForm";

// M4 : un propriétaire déjà connecté n'a rien à faire sur /connexion.
export default async function ConnexionPage() {
  const { owner } = await getViewer();
  if (owner) redirect("/");

  return (
    <div className="px-4 py-8 animate-fade-in">
      <h1 className="font-display text-4xl leading-none tracking-wide text-white">
        CONNE<span className="flame-text">XION</span>
      </h1>
      <p className="text-sm text-[color:var(--color-text-mute)] mt-2">
        Un code à 6 chiffres t&apos;est envoyé. Il ouvre une session sur cet appareil.
      </p>
      <LoginForm />
    </div>
  );
}
