import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {},
  // Route image des pronos (next/og) : polices lues sur le disque via
  // process.cwd() à l'exécution, invisibles pour le traçage statique —
  // à inclure explicitement dans la fonction déployée.
  outputFileTracingIncludes: {
    "/pronos-26-27/**": ["./src/app/fonts/*.woff"],
  },
};

export default nextConfig;
