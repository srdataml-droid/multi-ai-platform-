import { defineConfig } from "@playwright/test";

// The API (port 8000) and the worker are driven by the test itself; the web app is started here.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // One database and one job queue are shared by every spec, and specs run the worker
  // "once": in parallel, one spec's worker could take another spec's job. Run in series.
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    // Environments with a pre-installed chromium set PW_CHROMIUM_PATH instead of downloading one.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  // CI tests the production build, which is what users get: no on-demand page compiles
  // (a source of first-visit timeouts) and the production security headers. Locally the
  // dev server keeps edits live.
  webServer: {
    command: process.env.CI ? "npm run build && npm run start" : "npm run dev",
    url: "http://localhost:3000/login",
    reuseExistingServer: !process.env.CI,
    timeout: process.env.CI ? 300_000 : 120_000,
    // Extras on: the specs also cover the parked parts (stock, own agent, bridge, model
    // guesses), which stay in the code; the menu with them off is unit-tested (menu.test.ts).
    env: { NOVAXIS_API_URL: process.env.NOVAXIS_API_URL ?? "http://localhost:8000", NEXT_PUBLIC_NOVAXIS_EXTRAS: "1" },
  },
});
