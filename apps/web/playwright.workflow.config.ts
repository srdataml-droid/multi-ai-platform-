import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "callbacks.spec.ts",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://localhost:3108",
    video: "on",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: { command: "npx next start -p 3108", url: "http://localhost:3108/login", reuseExistingServer: !process.env.CI, timeout: 60000 },
});
