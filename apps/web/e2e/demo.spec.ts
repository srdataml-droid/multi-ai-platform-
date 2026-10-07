import { expect, test } from "@playwright/test";

test("account-free enquiry can be edited and approved without API traffic", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", r => { if (r.url().includes("/api/")) requests.push(r.url()); });
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: /A useful enquiry/ })).toBeVisible();
  await page.getByLabel("Name", { exact: true }).fill("Alex Demo");
  await page.getByRole("button", { name: "Send demo enquiry" }).click();
  await expect(page.getByRole("heading", { name: "Alex Demo" })).toBeVisible();
  await page.getByLabel("Callback window · change before approving").selectOption("Next working day, 16:00–18:00");
  await page.getByRole("button", { name: "Approve callback", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Next working day, 16:00–18:00" })).toBeVisible();
  await expect(page.getByText("Customer reply preview · not sent")).toBeVisible();
  await page.getByRole("button", { name: /Owner review/ }).click();
  await expect(page.getByRole("button", { name: "Approve callback", exact: true })).toBeDisabled();
  await page.reload();
  await page.getByRole("button", { name: /Callback plan/ }).click();
  await expect(page.getByRole("heading", { name: "No callback approved yet" })).toBeVisible();
  expect(requests).toEqual([]);
});

test("decline never adds a callback and reset clears the enquiry", async ({ page }) => {
  await page.goto("/demo");
  await page.getByRole("button", { name: "Send demo enquiry" }).click();
  await page.getByRole("button", { name: "Decline enquiry", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Enquiry declined", exact: true })).toBeVisible();
  await expect(page.getByText("Customer reply preview · not sent")).toHaveCount(0);
  await page.getByRole("button", { name: "Reset demo" }).click();
  await page.getByRole("button", { name: /Owner review/ }).click();
  await expect(page.getByText("Send a demo enquiry to see the review card.")).toBeVisible();
});

test("mobile demo has no overflow and requires contact fields", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/demo");
  await page.getByLabel("Email", { exact: true }).fill("");
  await page.getByRole("button", { name: "Send demo enquiry" }).click();
  await expect(page.getByRole("heading", { name: "Tell us what you need" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
