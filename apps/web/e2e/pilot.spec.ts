import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The Phase 1 pilot demo, in the browser: a customer message becomes a proposal, a staff
// member approves it, and the offered slots appear in the schedule. The worker runs with the
// scripted fake model so the test is deterministic; the API must already be running with
// NOVAXIS_LLM_PROVIDER=fake.

const API = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";
const REPO = process.env.NOVAXIS_REPO_ROOT ?? "../..";
const script = (marker: string) =>
  JSON.stringify([
    {
      text: "Sorry to hear that. I've passed this to the team to confirm a time.",
      calls: [{ tool: "propose_appointment", input: { service_code: "repair_visit", preferred_window: "next week", notes: marker } }],
    },
  ]);

function workerOnce(marker: string): void {
  execFileSync("uv", ["run", "python", "-m", "novaxis_worker.main", "--once"], {
    cwd: REPO,
    env: { ...process.env, NOVAXIS_LLM_PROVIDER: "fake", NOVAXIS_FAKE_SCRIPT: script(marker) },
    stdio: "pipe",
  });
}

async function login(page: import("@playwright/test").Page, email: string) {
  await page.goto("/login");
  await page.getByTestId("email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/inbox");
}

test("staff approves a proposal and sees the offered slots in the schedule", async ({ page, request }) => {
  const marker = `e2e-${Date.now()}`;
  const r = await request.post(`${API}/inbound/webchat/demo-hvac`, { data: { body: `boiler noise ${marker}`, name: marker } });
  expect(r.ok()).toBeTruthy();
  workerOnce(marker);

  await login(page, "owner@demo-hvac.test");
  // The inbox shows the contact (named with the marker) and the worker's reply as the last message.
  await expect(page.getByText(marker).first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("link", { name: /Approvals/ }).click();
  const card = page.locator("section", { hasText: marker }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(card).toBeHidden({ timeout: 15_000 });

  workerOnce(marker); // sends the offer message
  await page.getByRole("link", { name: "Schedule" }).click();
  await expect(page.getByTestId("appointment").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("held").first()).toBeVisible();
});

test("a viewer cannot approve", async ({ page, request }) => {
  const marker = `viewer-${Date.now()}`;
  await request.post(`${API}/inbound/webchat/demo-hvac`, { data: { body: `viewer check ${marker}` } });
  workerOnce(marker);
  await login(page, "viewer@demo-hvac.test");
  await page.getByRole("link", { name: /Approvals/ }).click();
  const card = page.locator("section", { hasText: marker }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/viewers cannot decide/)).toBeVisible();
});
