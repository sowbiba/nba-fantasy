"use client";

import { useEffect, useState, useTransition } from "react";
import { subscribePush, unsubscribePush, sendTestNotification } from "@/app/actions";

type Status = "checking" | "unsupported" | "ios-not-installed" | "not-configured" | "disabled" | "enabled";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

function isIos(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !("MSStream" in window);
}

function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i += 1) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export default function PushControls() {
  const [status, setStatus] = useState<Status>("checking");
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    async function check() {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        setStatus(isIos() && !isStandalone() ? "ios-not-installed" : "unsupported");
        return;
      }
      if (isIos() && !isStandalone()) {
        setStatus("ios-not-installed");
        return;
      }
      if (!VAPID_PUBLIC_KEY) {
        setStatus("not-configured");
        return;
      }
      try {
        // getRegistration() résout undefined si l'enregistrement a échoué
        // (ex. sw.js introuvable) — contrairement à `.ready`, qui resterait
        // en attente indéfiniment et laisserait la page bloquée sur "checking".
        const registration = await navigator.serviceWorker.getRegistration();
        if (!registration) {
          setStatus("disabled");
          return;
        }
        const sub = await registration.pushManager.getSubscription();
        setStatus(sub ? "enabled" : "disabled");
      } catch {
        setStatus("disabled");
      }
    }
    check();
  }, []);

  function enable() {
    setError(null);
    startTransition(async () => {
      try {
        if (!VAPID_PUBLIC_KEY) {
          setError("Rappels non configurés côté serveur (clé VAPID manquante).");
          return;
        }
        const permission = await Notification.requestPermission();
        if (permission !== "granted") {
          setError("Notifications refusées : active-les dans les réglages du téléphone.");
          return;
        }
        const registration = await navigator.serviceWorker.ready;
        const sub = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY) as BufferSource,
        });
        const result = await subscribePush(JSON.parse(JSON.stringify(sub)));
        if (!result.ok) {
          setError(result.error);
          return;
        }
        setStatus("enabled");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Échec de l'activation des rappels.");
      }
    });
  }

  function disable() {
    setError(null);
    startTransition(async () => {
      try {
        const registration = await navigator.serviceWorker.ready;
        const sub = await registration.pushManager.getSubscription();
        if (sub) {
          await unsubscribePush(sub.endpoint);
          await sub.unsubscribe();
        }
        setStatus("disabled");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Échec de la désactivation.");
      }
    });
  }

  function sendTest() {
    setTestResult(null);
    setError(null);
    startTransition(async () => {
      try {
        const result = await sendTestNotification();
        if (!result.ok) {
          setError(result.error);
          return;
        }
        setTestResult("Notification de test envoyée.");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Échec de l'envoi de la notification de test.");
      }
    });
  }

  if (status === "checking") return null;

  if (status === "unsupported") {
    return <p className="text-sm text-[color:var(--color-text-soft)]">Les notifications ne sont pas supportées par ce navigateur.</p>;
  }

  if (status === "not-configured") {
    return <p className="text-sm text-[color:var(--color-text-soft)]">Les rappels ne sont pas encore configurés côté serveur.</p>;
  }

  if (status === "ios-not-installed") {
    return (
      <p className="text-sm text-[color:var(--color-text-soft)]">
        Sur iPhone, ajoute d&apos;abord l&apos;app à l&apos;écran d&apos;accueil (Partager → Sur l&apos;écran d&apos;accueil), puis ouvre-la depuis l&apos;icône.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {status === "disabled" ? (
        <button onClick={enable} disabled={pending}
                className="rounded-[var(--radius-card-sm)] bg-[color:var(--color-accent)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          Activer les rappels
        </button>
      ) : (
        <>
          <button onClick={sendTest} disabled={pending}
                  className="rounded-[var(--radius-card-sm)] border border-white/10 px-4 py-2 text-sm text-[color:var(--color-text)] disabled:opacity-50">
            Envoyer une notification de test
          </button>
          <button onClick={disable} disabled={pending}
                  className="text-xs underline text-[color:var(--color-text-soft)] self-start">
            Désactiver
          </button>
        </>
      )}
      {testResult && <p className="text-xs text-[color:var(--color-text-soft)]">{testResult}</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
