"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { sendCode, verifyCode } from "./actions";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"email" | "code">("email");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const submitEmail = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await sendCode(email);
      if (res.ok) setStep("code");
      else setError(res.error ?? null);
    });
  };

  const submitCode = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await verifyCode(email, code);
      if (res.ok) {
        router.push("/");
        router.refresh();
      } else setError(res.error ?? null);
    });
  };

  const input = "w-full mt-2 px-4 py-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-white/10 text-white";
  const button = "w-full mt-4 py-3 rounded-[var(--radius-card)] font-display text-xl tracking-[0.15em] text-white bg-[color:var(--color-flame)] disabled:opacity-50";

  return step === "email" ? (
    <form onSubmit={submitEmail} className="mt-6">
      <label className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">E-mail</label>
      <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      <button disabled={pending} className={button}>{pending ? "…" : "RECEVOIR UN CODE"}</button>
      {error && <p role="alert" className="mt-2 text-xs text-[color:var(--color-crimson)]">{error}</p>}
    </form>
  ) : (
    <form onSubmit={submitCode} className="mt-6">
      <label className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">Code reçu par e-mail</label>
      <input inputMode="numeric" autoComplete="one-time-code" maxLength={10} required value={code}
             onChange={(e) => setCode(e.target.value)} className={`${input} tracking-[0.5em] text-center text-2xl`} />
      <button disabled={pending} className={button}>{pending ? "…" : "VALIDER"}</button>
      {error && <p role="alert" className="mt-2 text-xs text-[color:var(--color-crimson)]">{error}</p>}
      <button type="button" onClick={() => setStep("email")} className="w-full mt-3 text-xs text-[color:var(--color-text-mute)] underline">
        Changer d&apos;e-mail / renvoyer un code
      </button>
    </form>
  );
}
