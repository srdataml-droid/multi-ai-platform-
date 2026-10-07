import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "demo.spec.ts",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3107",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: {
    command: "npx next start -p 3107",
    url: "http://127.0.0.1:3107/demo",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
