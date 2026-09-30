// Enregistrement automatique (pronos 2026-27) : anti-rebond + file d'envoi
// sans parallélisme ni perte de la dernière saisie. Pur (aucune dépendance
// React/Next), testé dans autosave.test.ts avec de fausses horloges.
//
// Règles :
// - `schedule(v)` mémorise la valeur la plus récente et (re)lance le délai ;
// - un seul envoi à la fois : une saisie arrivée pendant un envoi est
//   renvoyée juste après (la dernière gagne), jamais perdue ;
// - un échec laisse l'état « erreur » ; la saisie suivante renvoie la
//   carte complète (chaque envoi contient tout le prono).

export type AutosaveStatus = "pending" | "saving" | "saved" | "error";
export type AutosaveState = { status: AutosaveStatus; error?: string };

type SaveResult = { ok: true } | { ok: false; error: string };

const NETWORK_ERROR = "Enregistrement impossible (problème de connexion ?). Réessaie.";

export function createAutosave<T>(opts: {
  save: (value: T) => Promise<SaveResult>;
  onState: (state: AutosaveState) => void;
  delay?: number;
}) {
  const delay = opts.delay ?? 800;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let latest: { value: T } | null = null;
  let inflight = false;
  let current: AutosaveState | null = null;

  function emit(next: AutosaveState) {
    if (current && current.status === next.status && current.error === next.error) return;
    current = next;
    opts.onState(next);
  }

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  async function run() {
    if (inflight || !latest) return;
    inflight = true;
    let lastError: string | null = null;
    while (latest) {
      clearTimer();
      const { value } = latest;
      latest = null;
      emit({ status: "saving" });
      try {
        const r = await opts.save(value);
        lastError = r.ok ? null : r.error;
      } catch {
        lastError = NETWORK_ERROR;
      }
    }
    inflight = false;
    emit(lastError ? { status: "error", error: lastError } : { status: "saved" });
  }

  return {
    schedule(value: T) {
      latest = { value };
      if (!inflight) emit({ status: "pending" });
      clearTimer();
      timer = setTimeout(() => {
        timer = null;
        void run();
      }, delay);
    },
    /** Envoie tout de suite la saisie en attente (ex. onglet masqué). */
    flush() {
      clearTimer();
      void run();
    },
    /** Abandonne la saisie en attente (démontage, prono clos). */
    cancel() {
      clearTimer();
      latest = null;
    },
  };
}
