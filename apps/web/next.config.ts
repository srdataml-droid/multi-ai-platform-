import type { NextConfig } from "next";

// In dev, /api/* is proxied to the FastAPI process so the browser never deals
// with CORS and the page can call the API by relative path. In production the
// same paths are served by the platform's routing. See ADR 0001.
const apiBase = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";

// The dashboard must never be framed (clickjacking an Approve button), must not sniff
// content types, and may load scripts only from itself. Dev needs eval for fast refresh.
const dev = process.env.NODE_ENV !== "production";
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "connect-src 'self' https://*.supabase.co",
  "worker-src 'self'",
  "manifest-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");
const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  output: "standalone",
  // The dev badge sits over the menu's "Sign out" link.
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
