import { execFileSync } from "node:child_process";
import { createServer, type Server } from "node:http";
import { expect, test } from "@playwright/test";

// The widget on a business's own website: a different origin from both the dashboard and
// the API, so every call it makes is cross-origin. A tiny server on its own port plays the
// business's site; the widget script and the API are the real local servers.

const API = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";
const WEB = "http://localhost:3000";
const REPO = process.env.NOVAXIS_REPO_ROOT ?? "../..";
const SITE = "http://127.0.0.1:5599/";
const PAGE = `<!doctype html><title>A plumber</title><h1>Bob's Plumbing</h1>
<script src="${WEB}/widget.js" data-tenant="demo-hvac" data-api="${API}"></script>`;

let site: Server;
test.beforeAll(async () => {
  site = createServer((_req, res) => res.writeHead(200, { "Content-Type": "text/html" }).end(PAGE));
  await new Promise<void>((resolve) => site.listen(5599, "127.0.0.1", resolve));
});
test.afterAll(() => site.close());

test("the chat widget works when embedded on another website", async ({ page }) => {
  const marker = `site-${Date.now()}`;
  await page.goto(SITE);
  await page.getByTitle("Chat with us").click();
  await page.getByPlaceholder("Type a message").fill(`my radiator is cold ${marker}`);
  const sent = page.waitForResponse((r) => r.url().startsWith(`${API}/inbound/webchat/demo-hvac`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Send" }).click();
  expect((await sent).status()).toBe(200);

  execFileSync("uv", ["run", "python", "-m", "novaxis_worker.main", "--once"], {
    cwd: REPO,
    env: { ...process.env, NOVAXIS_LLM_PROVIDER: "fake", NOVAXIS_FAKE_SCRIPT: JSON.stringify([{ text: `Sorry to hear that ${marker}`, calls: [] }]) },
    stdio: "pipe",
  });
  await expect(page.getByText(`Sorry to hear that ${marker}`)).toBeVisible({ timeout: 15_000 });
});

test("a visitor can speak a message and hear the reply", async ({ page }) => {
  const marker = `voice-${Date.now()}`;
  // Headless browsers have no microphone or speakers: stand-ins return a transcript and
  // record what would be spoken. The widget code under test is the real one.
  await page.addInitScript((heard: string) => {
    const w = window as unknown as Record<string, unknown>;
    w.__spoken = [];
    class FakeRecognition {
      lang = "";
      interimResults = false;
      maxAlternatives = 1;
      onresult: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        setTimeout(() => {
          this.onresult?.({ results: [[{ transcript: heard }]] });
          this.onend?.();
        }, 50);
      }
    }
    w.SpeechRecognition = FakeRecognition;
    Object.defineProperty(window, "speechSynthesis", {
      value: { speak: (u: { text: string }) => (w.__spoken as string[]).push(u.text), cancel: () => undefined },
    });
    w.SpeechSynthesisUtterance = class { lang = ""; constructor(public text: string) {} };
  }, `my boiler is leaking ${marker}`);

  await page.goto(SITE);
  await page.getByTitle("Chat with us").click();
  await page.getByTitle("Read replies aloud").click();
  const sent = page.waitForRequest((r) => r.url().startsWith(`${API}/inbound/webchat/demo-hvac`) && r.method() === "POST");
  await page.getByTitle("Speak your message").click();
  expect((await sent).postDataJSON().body).toBe(`my boiler is leaking ${marker}`);

  execFileSync("uv", ["run", "python", "-m", "novaxis_worker.main", "--once"], {
    cwd: REPO,
    env: { ...process.env, NOVAXIS_LLM_PROVIDER: "fake", NOVAXIS_FAKE_SCRIPT: JSON.stringify([{ text: `On our way ${marker}`, calls: [] }]) },
    stdio: "pipe",
  });
  await expect(page.getByText(`On our way ${marker}`)).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.join(" | "))).toContain(`On our way ${marker}`);
});
