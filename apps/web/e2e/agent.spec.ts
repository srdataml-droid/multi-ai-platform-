import { expect, test } from "@playwright/test";

// The owner creates a key for their own agent in Settings; it is shown once and opens the
// agent API (docs/agent-api.md).

const API = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";

test("the owner creates an agent key that opens the agent API", async ({ page, request }) => {
  await page.goto("/login");
  await page.getByTestId("email").fill("owner@demo-hvac.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/inbox");
  await page.goto("/settings");
  await expect(page.getByText("Your own agent (agent API)")).toBeVisible();
  await expect(page.getByTestId("assistant-mode")).toHaveValue("built_in");
  await page.getByRole("button", { name: "Create key" }).click();
  const shown = page.getByTestId("new-agent-key");
  await expect(shown).toContainText("nvx_agent_");
  const key = (await shown.locator("code").textContent())?.trim() ?? "";

  const r = await request.get(`${API}/agent/v1/tools`, { headers: { Authorization: `Bearer ${key}` } });
  expect(r.status()).toBe(200);
  expect((await r.json()).tools[0].function.name).toBe("reply");
  await page.getByRole("button", { name: "I have copied it" }).click();
  await expect(shown).toBeHidden();

  // Push instead of polling: set a webhook, get its signing secret once, send a test.
  const hook = page.locator("[data-testid^=webhook-]").first();
  await hook.fill("http://127.0.0.1:9/novaxis"); // nothing listens there
  await page.getByRole("button", { name: "Save", exact: true }).first().click();
  await expect(page.getByTestId("webhook-secret")).toContainText("whsec_");
  await page.getByRole("button", { name: "Send test" }).first().click();
  await expect(page.getByText(/not reached/).first()).toBeVisible();
});
