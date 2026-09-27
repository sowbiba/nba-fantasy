import "server-only";
import webpush from "web-push";
import { adminClient } from "@/lib/supabase/admin";

export type PushMessage = { title: string; body: string; url?: string; ttlSeconds?: number };

type Subscription = { id: number; endpoint: string; p256dh: string; auth: string };

type Db = {
  from(table: "push_subscriptions"): {
    select(cols: string): Promise<{ data: Subscription[] | null }>;
    delete(): { eq(col: string, value: number): Promise<{ error: unknown }> };
    update(values: { last_ok_at: string }): { eq(col: string, value: number): Promise<{ error: unknown }> };
  };
};

type SendPushResult = { statusCode?: number } | Error | unknown;

export type PushOptions = { TTL: number; urgency: "high" };

export type NotifyDeps = {
  sendPush?: (
    sub: { endpoint: string; keys: { p256dh: string; auth: string } },
    payload: string,
    options: PushOptions,
  ) => Promise<unknown>;
  sendTelegram?: (text: string) => Promise<boolean>;
  db?: Db;
};

const DEFAULT_TTL_SECONDS = 4 * 7 * 24 * 60 * 60; // 4 semaines (défaut web-push), si aucune expiry connue

/** Client Supabase avec la forme minimale utilisée ici (accès via la clé
 *  service, cf. push_subscriptions, migration 024). */
function defaultDb(): Db {
  return adminClient() as unknown as Db;
}

let vapidConfigured = false;

function configureVapid(): boolean {
  const publicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const privateKey = process.env.VAPID_PRIVATE_KEY;
  if (!publicKey || !privateKey) return false;
  if (!vapidConfigured) {
    const subject = `mailto:${process.env.OWNER_EMAIL ?? "owner@example.com"}`;
    webpush.setVapidDetails(subject, publicKey, privateKey);
    vapidConfigured = true;
  }
  return true;
}

async function defaultSendPush(
  sub: { endpoint: string; keys: { p256dh: string; auth: string } },
  payload: string,
  options: PushOptions,
): Promise<unknown> {
  return webpush.sendNotification(sub, payload, options);
}

async function defaultSendTelegram(text: string): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return false;
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    });
    return res.ok;
  } catch (e) {
    console.error("Échec de l'envoi Telegram :", e instanceof Error ? e.message : e);
    return false;
  }
}

function statusCodeOf(err: SendPushResult): number | undefined {
  if (err && typeof err === "object" && "statusCode" in err) {
    const code = (err as { statusCode?: unknown }).statusCode;
    return typeof code === "number" ? code : undefined;
  }
  return undefined;
}

/** Envoie `msg` à tous les abonnements push (web-push) ; supprime les
 *  abonnements périmés (404/410), marque `last_ok_at` sur les succès. Si
 *  aucun envoi push n'a réussi, se replie sur Telegram quand configuré. */
export async function notifyAll(msg: PushMessage, deps: NotifyDeps = {}): Promise<{ push: number; telegram: boolean }> {
  const db = deps.db ?? defaultDb();
  const sendTelegram = deps.sendTelegram ?? defaultSendTelegram;
  const hasVapid = configureVapid();
  const sendPush = deps.sendPush ?? defaultSendPush;

  const { data: subs } = await db.from("push_subscriptions").select("id, endpoint, p256dh, auth");
  const { ttlSeconds, ...body } = msg;
  const payload = JSON.stringify(body);
  const options: PushOptions = { TTL: ttlSeconds ?? DEFAULT_TTL_SECONDS, urgency: "high" };

  let pushOk = 0;
  if (hasVapid || deps.sendPush) {
    for (const sub of subs ?? []) {
      try {
        await sendPush({ endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } }, payload, options);
        pushOk += 1;
        await db.from("push_subscriptions").update({ last_ok_at: new Date().toISOString() }).eq("id", sub.id);
      } catch (e) {
        const code = statusCodeOf(e);
        if (code === 404 || code === 410) {
          await db.from("push_subscriptions").delete().eq("id", sub.id);
        } else {
          console.error("Échec de l'envoi push :", e instanceof Error ? e.message : e);
        }
      }
    }
  }

  let telegram = false;
  if (pushOk === 0) {
    telegram = await sendTelegram(`${msg.title}\n${msg.body}`);
  }

  return { push: pushOk, telegram };
}
