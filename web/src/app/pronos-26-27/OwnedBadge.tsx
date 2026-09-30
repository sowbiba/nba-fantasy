"use client";

import { useStoredToken } from "./token-store";

/** « Le mien » sur la liste, si cet appareil détient le jeton du prono. */
export default function OwnedBadge({ id }: { id: string }) {
  const token = useStoredToken(id);
  if (!token) return null;
  return (
    <span className="text-[9px] uppercase tracking-[0.18em] px-2 py-0.5 rounded-full border border-[color:var(--color-gold)]/40 text-[color:var(--color-gold)]">
      Le mien
    </span>
  );
}
