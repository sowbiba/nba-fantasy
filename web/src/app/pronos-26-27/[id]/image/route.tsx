import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { getPronoCore } from "@/app/pronos-26-27/core";
import { LEAGUE_EXPECTED_WINS, leagueWinsTotal, standingsFromWins, type Conference, type StandingsRow } from "@/lib/pronos";
import { standingsTint, standingsZone } from "@/lib/display";

// Image partageable d'un prono (bouton « Partager ») : nom + classement
// projeté des deux conférences. Rendu satori (next/og) : le nom est un
// simple nœud texte, jamais interprété comme du HTML. Polices lues sur le
// disque (src/app/fonts, woff — satori ne lit pas le woff2), jamais
// téléchargées ; tracées pour le déploiement via outputFileTracingIncludes
// (next.config.ts).

const WIDTH = 1080;
const HEIGHT = 1350;

const COLORS = {
  ink: "#0a0a0d",
  text: "#f5f5f7",
  soft: "#b8b9c6",
  mute: "#6d6e7f",
  gold: "#f7c948",
  flame: "#ff5b1f",
};

type FontSpec = { name: string; data: Buffer; weight: 400 | 700; style: "normal" };

let fontsPromise: Promise<FontSpec[]> | null = null;

function loadFonts(): Promise<FontSpec[]> {
  if (!fontsPromise) {
    const dir = join(process.cwd(), "src", "app", "fonts");
    fontsPromise = Promise.all([
      readFile(join(dir, "bebas-neue-400.woff")),
      readFile(join(dir, "space-grotesk-400.woff")),
      readFile(join(dir, "space-grotesk-700.woff")),
    ]).then(([bebas, sg400, sg700]) => [
      { name: "Bebas Neue", data: bebas, weight: 400, style: "normal" },
      { name: "Space Grotesk", data: sg400, weight: 400, style: "normal" },
      { name: "Space Grotesk", data: sg700, weight: 700, style: "normal" },
    ]);
    // Un échec (fichier absent) ne doit pas rester en cache pour toujours.
    fontsPromise.catch(() => {
      fontsPromise = null;
    });
  }
  return fontsPromise;
}

function ConferenceColumn({ conference, rows }: { conference: Conference; rows: StandingsRow[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
      <div
        style={{
          display: "flex",
          fontSize: 22,
          letterSpacing: 5,
          textTransform: "uppercase",
          color: COLORS.mute,
          marginBottom: 12,
        }}
      >
        {`Conférence ${conference}`}
      </div>
      {rows.map((r, i) => {
        const rank = i + 1;
        const tint = standingsTint(rank);
        const next = rows[i + 1];
        const separator = !!next && standingsZone(rank + 1) !== standingsZone(rank);
        return (
          <div
            key={r.team}
            style={{
              display: "flex",
              alignItems: "center",
              height: 58,
              padding: "0 16px",
              backgroundColor: tint > 0 ? `rgba(255, 255, 255, ${tint})` : "transparent",
              borderBottom: separator ? "2px solid rgba(255, 255, 255, 0.18)" : "1px solid rgba(255, 255, 255, 0.04)",
            }}
          >
            <div style={{ display: "flex", width: 44, fontSize: 24, color: COLORS.mute }}>{String(rank)}</div>
            <div style={{ display: "flex", flex: 1, fontSize: 30, fontWeight: 700, color: COLORS.text }}>{r.team}</div>
            <div style={{ display: "flex", fontSize: 28, color: COLORS.soft }}>{`${r.wins}-${r.losses}`}</div>
          </div>
        );
      })}
    </div>
  );
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const prono = await getPronoCore(id);
  if (!prono) {
    return new Response("Prono introuvable", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }

  const standings = standingsFromWins(prono.wins);
  const total = leagueWinsTotal(prono.wins);

  try {
    const fonts = await loadFonts();
    const image = new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            padding: "64px 56px 48px",
            fontFamily: "Space Grotesk",
            color: COLORS.text,
            backgroundColor: COLORS.ink,
            backgroundImage: "radial-gradient(900px 420px at 50% -120px, rgba(255, 91, 31, 0.22), transparent 70%)",
          }}
        >
          <div style={{ display: "flex", fontSize: 24, letterSpacing: 6, color: COLORS.gold, textTransform: "uppercase" }}>
            Pronos NBA 2026-27
          </div>
          <div
            style={{
              display: "flex",
              fontFamily: "Bebas Neue",
              fontSize: 96,
              lineHeight: 1,
              marginTop: 12,
              color: COLORS.text,
            }}
          >
            {prono.name}
          </div>
          <div style={{ display: "flex", fontSize: 22, color: COLORS.mute, marginTop: 8, marginBottom: 36 }}>
            Bilans projetés en saison régulière
          </div>
          <div style={{ display: "flex", gap: 40, flex: 1 }}>
            <ConferenceColumn conference="Est" rows={standings.Est} />
            <ConferenceColumn conference="Ouest" rows={standings.Ouest} />
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 20,
              color: COLORS.mute,
              marginTop: 24,
            }}
          >
            <div style={{ display: "flex" }}>1-6 playoffs · 7-10 play-in</div>
            <div style={{ display: "flex" }}>{`${total} / ${LEAGUE_EXPECTED_WINS} victoires`}</div>
          </div>
        </div>
      ),
      { width: WIDTH, height: HEIGHT, fonts },
    );
    // Rendu complet ici (et non en flux) : une erreur de rendu devient une
    // vraie réponse 500 au lieu d'un PNG tronqué servi avec un statut 200.
    const png = await image.arrayBuffer();
    return new Response(png, {
      status: 200,
      headers: { "content-type": "image/png", "cache-control": "no-store" },
    });
  } catch (e) {
    console.error("image prono :", e instanceof Error ? e.message : e);
    return new Response("Image indisponible", {
      status: 500,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
}
