import { expect, test } from "@playwright/test";

// Chunk 11 in the browser: a new business connects booking software that has no API,
// uploads its diary export, and sees the hand-off list on the Schedule page.
// Needs the API on :8000 (local env, seeded). SHOTS=<dir> also saves screenshots.

const API = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";

test("connect the booking bridge and import a diary export", async ({ page, request }) => {
  const stamp = Date.now();
  const r = await request.post(`${API}/signup`, { data: { business_name: `Bridge E2E ${stamp}`, email: `bridge-${stamp}@e2e.test`, pack_id: "hvac" } });
  expect(r.ok()).toBeTruthy();
  const token = (await r.json()).token as string;
  const auth = { Authorization: `Bearer ${token}` };
  const wizard = (await (await request.get(`${API}/onboarding`, { headers: auth })).json()).wizard;
  wizard.on_call = { name: "Sam", phone: "+447700900123", email: null };
  expect((await request.post(`${API}/onboarding`, { headers: auth, data: wizard })).ok()).toBeTruthy();

  await page.goto("/login");
  await page.evaluate((t) => localStorage.setItem("novaxis:token", t), token);
  await page.goto("/settings");
  await page.getByPlaceholder("e.g. your job management system").fill("Acme Jobs");
  await page.getByPlaceholder("office@yourbusiness.co.uk").fill("office@e2e.test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("no diary export from Acme Jobs yet")).toBeVisible();

  const day = new Date(Date.now() + 3 * 86400_000);
  const d = `${String(day.getDate()).padStart(2, "0")}/${String(day.getMonth() + 1).padStart(2, "0")}/${day.getFullYear()}`;
  const csv = `Start,End,Title,Status\n${d} 09:00,${d} 10:00,Existing job,Scheduled\n${d} 11:00,${d} 12:00,Called off,Cancelled\n`;
  await page.getByTestId("bridge-upload").setInputFiles({ name: "diary.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("Imported 1 of 2 rows, skipped 1.")).toBeVisible();
  await expect(page.getByText("diary current")).toBeVisible();
  if (process.env.SHOTS) await page.getByText("Booking software without an API").screenshot({ path: `${process.env.SHOTS}/11-bridge-settings.png` });

  await page.getByRole("link", { name: "Schedule" }).click();
  await expect(page.getByText("To key into Acme Jobs (0)")).toBeVisible();
});
