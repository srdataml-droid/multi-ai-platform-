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
