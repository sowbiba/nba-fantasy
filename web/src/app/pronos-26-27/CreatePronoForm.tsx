"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { createProno } from "./actions";
import { storeToken } from "./token-store";

export default function CreatePronoForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      let result: Awaited<ReturnType<typeof createProno>>;
      try {
        result = await createProno(name);
      } catch {
        setError("Création impossible (problème de connexion ?). Réessaie.");
        return;
      }
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (!storeToken(result.data.id, result.data.token)) {
        setError(
          "Prono créé, mais ce navigateur refuse le stockage local : tu ne pourras pas le modifier. Désactive la navigation privée et recrée-le sous un autre nom.",
        );
        return;
      }
      router.push(`/pronos-26-27/${result.data.id}`);
    });
  }

  const trimmedLength = name.trim().length;

  return (
    <form onSubmit={onSubmit} className="surface p-4 flex flex-col gap-3">
      <label htmlFor="prono-name" className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
        Faire mon prono
      </label>
      <div className="flex gap-2">
        <input
          id="prono-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          minLength={2}
          maxLength={30}
          required
          autoComplete="nickname"
          placeholder="Ton nom (2 à 30 caractères)"
          className="flex-1 min-w-0 h-11 px-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)] placeholder:text-[color:var(--color-text-dim)] focus:outline-none focus:border-[color:var(--color-flame)]"
        />
        <button
          type="submit"
          disabled={pending || trimmedLength < 2}
          className="h-11 px-4 rounded-[var(--radius-card-sm)] bg-[color:var(--color-flame)] text-black font-semibold text-sm disabled:opacity-40"
        >
          {pending ? "Création…" : "Créer"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-[color:var(--color-crimson)]">
          {error}
        </p>
      )}
      <p className="text-[11px] text-[color:var(--color-text-mute)]">
        Ton prono ne sera modifiable que depuis cet appareil et ce navigateur.
      </p>
    </form>
  );
}
