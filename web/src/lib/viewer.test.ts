import { afterEach, describe, expect, it, vi } from "vitest";
import { getViewer, ownerDb } from "./viewer";

const OWNER = "moi@exemple.fr";

function client(email: string | null) {
  return async () => ({ auth: { getUser: async () => ({ data: { user: email === null ? null : { email } } }) } });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getViewer", () => {
  it("owner: true pour le propriétaire, casse et espaces ignorés", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    expect(await getViewer(client(" Moi@Exemple.fr "))).toEqual({ owner: true });
  });

  it("owner: false pour un autre e-mail", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    expect(await getViewer(client("autre@exemple.fr"))).toEqual({ owner: false });
  });

  it("owner: false sans utilisateur", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    expect(await getViewer(client(null))).toEqual({ owner: false });
  });

  it("owner: false si getUser lève (session expirée, cookies absents)", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    const throwing = async (): Promise<never> => {
      throw new Error("session illisible");
    };
    expect(await getViewer(throwing)).toEqual({ owner: false });
  });

  it("owner: false sans OWNER_EMAIL configuré", async () => {
    vi.stubEnv("OWNER_EMAIL", "");
    expect(await getViewer(client(OWNER))).toEqual({ owner: false });
  });
});

describe("ownerDb", () => {
  it("null si non propriétaire", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    expect(await ownerDb(client("autre@exemple.fr"))).toBeNull();
  });

  it("null si la session lève une erreur", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    const throwing = async (): Promise<never> => {
      throw new Error("boom");
    };
    expect(await ownerDb(throwing)).toBeNull();
  });

  it("client service (adminClient) si propriétaire", async () => {
    vi.stubEnv("OWNER_EMAIL", OWNER);
    vi.stubEnv("SUPABASE_SERVICE_KEY", "test-service-key");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    const db = await ownerDb(client(OWNER));
    expect(db).not.toBeNull();
  });
});
