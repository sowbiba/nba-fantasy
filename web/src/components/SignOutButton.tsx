"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "@/app/actions";

export default function SignOutButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button onClick={() => startTransition(async () => { await signOut(); router.refresh(); })}
            disabled={pending} className="text-[11px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)] underline">
      Déconnexion
    </button>
  );
}
