import type { NextConfig } from "next";

// In dev, /api/* is proxied to the FastAPI process so the browser never deals
// with CORS and the page can call the API by relative path. In production the
// same paths are served by the platform's routing. See ADR 0001.
const apiBase = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
