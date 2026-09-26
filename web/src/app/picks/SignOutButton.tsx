"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "@/app/actions";

export default function SignOutButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button onClick={() => startTransition(async () => { await signOut(); router.refresh(); })}
            disabled={pending} className="text-xs underline text-[color:var(--color-text-soft)]">
      Déconnexion
    </button>
  );
}
