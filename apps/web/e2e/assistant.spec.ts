import { test, expect } from "@playwright/test";

test("Studio chats through the widget channel and preserves business facts when saving style", async ({ page }) => {
  let settings = {
    widget_origins: [] as string[],
    pack_id: "hvac", tone: "Friendly and brief", service_area: ["SW1"],
    services: [{ code: "repair", name: "Boiler repair", duration_minutes: 60 }],
    faqs: [{ question: "Do you offer quotes?", answer: "Yes, after inspection." }],
    business_hours: { mon: { open: "09:00", close: "17:00" } },
    channels: { webchat: { enabled: true } },
  };
  let sent = false;
  let observed = false;
  const business = () => ({ tenant: { name: "Studio Heating", slug: "studio-heating", pack_id: "hvac", worker_enabled: true }, settings });
  await page.addInitScript(() => localStorage.setItem("novaxis:token", "test-owner-token"));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown = {};
    if (path === "/api/me") data = { role: "owner", email: "studio@example.test", tenant: { ...business().tenant, onboarded: true, timezone: "Europe/London" } };
    else if (path === "/api/pack") data = { name: "Heating & cooling", vocabulary: {}, dashboard: {} };
    else if (path === "/api/approvals") data = { count: 0 };
    else if (path === "/api/settings/widget") data = { snippet: '<script src="https://studio.test/widget.js" data-tenant="studio-heating" data-api="https://api.studio.test"></script>' };
    else if (path === "/api/settings") {
      if (request.method() === "PUT") settings = request.postDataJSON().settings;
      data = business();
    } else if (path === "/api/settings/assistant") data = { provider: "fake", scripted: true, models: { responses: "fake", classification: "fake", summaries: "fake" }, latest_worker_call: observed ? { model: "fake", at: "2026-10-08T12:00:00Z" } : null };
    else if (path === "/api/inbound/webchat/studio-heating" && request.method() === "POST") {
      expect(request.headers().authorization).toBeUndefined();
      expect(request.postDataJSON().body).toBe("When are you open?");
      sent = true;
      data = { visitor_token: "test-visitor", message_id: "incoming", conversation_id: "conversation-1" };
    } else if (path.endsWith("/messages")) {
      expect(new URL(request.url()).searchParams.get("visitor_token")).toBe("test-visitor");
      observed = sent;
      data = { conversation_id: "conversation-1", messages: sent ? [{ id: "incoming", direction: "inbound", author: "customer", body: "When are you open?" }, { id: "reply", direction: "outbound", author: "worker", body: "We open on Monday at 9am." }] : [] };
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "Assistant Studio", exact: true })).toBeVisible();
  await expect(page.getByText("Scripted demo provider")).toBeVisible();
  await expect(page.getByText("No worker call recorded yet")).toBeVisible();
  await expect(page.getByText("Boiler repair", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/assistant-studio.png", fullPage: true });
  await page.getByRole("button", { name: "When are you open?", exact: true }).click();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("We open on Monday at 9am.");
  await expect(page.getByRole("link", { name: "View conversation in Inbox" })).toHaveAttribute("href", "/conversations/conversation-1");
  await page.getByLabel("Reply style").fill("Professional, clear, no jargon.");
  await page.getByRole("button", { name: "Save reply style" }).click();
  await expect(page.getByText("Saved for future replies")).toBeVisible();
  expect(settings.tone).toBe("Professional, clear, no jargon.");
  expect(settings.service_area).toEqual(["SW1"]);
  expect(settings.faqs).toHaveLength(1);
  await page.getByLabel("Your website addresses").fill("https://www.studio-heating.test/contact\nhttps://studio-heating.test/");
  await page.getByRole("button", { name: "Save websites", exact: true }).click();
  await expect(page.getByText("Website access saved", { exact: true })).toBeVisible();
  expect(settings.widget_origins).toEqual(["https://www.studio-heating.test", "https://studio-heating.test"]);
  expect(settings.tone).toBe("Professional, clear, no jargon.");
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.getByRole("log")).not.toContainText("We open on Monday at 9am.");
});

test("Studio blocks chat when the business channel is off and shows unknown model status", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("novaxis:token", "test-owner-token"));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/settings/assistant") { await route.fulfill({ status: 404, json: { detail: "Not Found" } }); return; }
    const data = path === "/api/settings" ? { tenant: { name: "Offline business", slug: "offline", worker_enabled: true }, settings: { channels: { webchat: { enabled: false } } } }
      : path === "/api/me" ? { role: "owner", email: "studio@example.test", tenant: { name: "Offline business", onboarded: true } }
      : path === "/api/pack" ? { name: "HVAC", vocabulary: {}, dashboard: {} } : { count: 0 };
    await route.fulfill({ json: data });
  });
  await page.goto("/assistant");
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await expect(page.getByText("Model status unavailable.", { exact: false })).toBeVisible();
  await expect(page.getByText("Enable the assistant and Website chat", { exact: false })).toBeVisible();
});
