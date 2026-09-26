import { defineConfig } from "@playwright/test";

// The API (port 8000) and the worker are driven by the test itself; the web app is started here.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    // Environments with a pre-installed chromium set PW_CHROMIUM_PATH instead of downloading one.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000/login",
    reuseExistingServer: true,
    timeout: 120_000,
    env: { NOVAXIS_API_URL: process.env.NOVAXIS_API_URL ?? "http://localhost:8000" },
  },
});
