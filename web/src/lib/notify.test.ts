import { describe, expect, it } from "vitest";
import { notifyAll } from "./notify";

type Row = { id: number; endpoint: string; p256dh: string; auth: string };

function fakeDb(rows: Row[]) {
  const store = [...rows];
  return {
    from() {
      return {
        select: async () => ({ data: store }),
        delete: () => ({
          eq: async (_col: string, value: number) => {
            const idx = store.findIndex((r) => r.id === value);
            if (idx !== -1) store.splice(idx, 1);
            return { error: null };
          },
        }),
        update: () => ({
          eq: async () => ({ error: null }),
        }),
      };
    },
    store,
  };
}

describe("notifyAll", () => {
  it("supprime l'abonnement en 410 et ne notifie pas Telegram si un envoi a réussi", async () => {
    const db = fakeDb([
      { id: 1, endpoint: "https://push/1", p256dh: "p1", auth: "a1" },
      { id: 2, endpoint: "https://push/2", p256dh: "p2", auth: "a2" },
    ]);
    let telegramCalled = false;
    const result = await notifyAll(
      { title: "Titre", body: "Corps" },
      {
        db,
        sendPush: async (sub) => {
          if (sub.endpoint === "https://push/2") {
            const err = Object.assign(new Error("gone"), { statusCode: 410 });
            throw err;
          }
          return { statusCode: 201 };
        },
        sendTelegram: async () => {
          telegramCalled = true;
          return true;
        },
      },
    );
    expect(result.push).toBe(1);
    expect(result.telegram).toBe(false);
    expect(telegramCalled).toBe(false);
    expect(db.store.map((s) => s.id)).toEqual([1]);
  });

  it("se replie sur Telegram quand tous les envois push échouent", async () => {
    const db = fakeDb([{ id: 1, endpoint: "https://push/1", p256dh: "p1", auth: "a1" }]);
    const result = await notifyAll(
      { title: "Titre", body: "Corps" },
      {
        db,
        sendPush: async () => {
          throw new Error("échec réseau");
        },
        sendTelegram: async () => true,
      },
    );
    expect(result.push).toBe(0);
    expect(result.telegram).toBe(true);
  });

  it("ne plante pas sans abonnement ni Telegram configuré", async () => {
    const db = fakeDb([]);
    const result = await notifyAll(
      { title: "Titre", body: "Corps" },
      { db, sendPush: async () => ({ statusCode: 201 }), sendTelegram: async () => false },
    );
    expect(result).toEqual({ push: 0, telegram: false });
  });
});
