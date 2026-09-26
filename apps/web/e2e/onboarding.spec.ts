import { expect, test, type Page } from "@playwright/test";

// Chunk 10 in the browser: a new business signs up, walks the setup wizard, picks a plan
// (demo billing), and a Novaxis operator finds it in the console and enters it with audit.
// Needs the API on :8000 (local env, seeded). SHOTS=<dir> also saves screenshots.

const shot = async (page: Page, name: string) => {
  if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/${name}.png`, fullPage: true });
};

test("sign up, onboard, pay, and the operator enters with an audit trail", async ({ page }) => {
  const stamp = Date.now();
  const business = `E2E Heating ${stamp}`;

  await page.goto("/signup");
  await page.getByTestId("business-name").fill(business);
  await page.getByTestId("signup-email").fill(`owner-${stamp}@e2e.test`);
  await page.getByText("Heating, cooling").click();
  await shot(page, "01-signup");
  await page.getByRole("button", { name: "Create my account" }).click();

  await page.waitForURL("**/onboarding");
  await expect(page.getByText("Set up your AI worker: Business")).toBeVisible();
  await shot(page, "02-wizard-business");
  for (const step of ["Hours", "Services", "Area", "Channels", "Calendar"]) {
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText(`Set up your AI worker: ${step}`)).toBeVisible();
    if (step === "Services") await shot(page, "03-wizard-services");
  }
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Name").fill("Sam On-Call");
  await page.getByLabel("Mobile").fill("+447700900123");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Repair visit (90 min)")).toBeVisible();
  await shot(page, "04-wizard-review");
  await page.getByRole("button", { name: "Confirm and go live" }).click();
  await page.waitForURL("**/inbox");
  await expect(page.getByRole("link", { name: "Free trial" })).toBeVisible();

  await page.getByRole("link", { name: "Billing" }).click();
  await expect(page.getByTestId("demo-billing")).toBeVisible();
  await expect(page.getByText("0 of 100 AI replies used")).toBeVisible();
  await shot(page, "05-billing-trial");
  await page.getByRole("button", { name: "Choose Pilot" }).click();
  await expect(page.getByText("Demo billing: activated on pilot. No payment was taken.")).toBeVisible();
  await expect(page.getByText("Current")).toBeVisible();
  await expect(page.getByRole("link", { name: "Free trial" })).toHaveCount(0);
  await shot(page, "06-billing-active");

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");
  await page.getByTestId("email").fill("operator@novaxis.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/operator");
  const row = page.getByRole("row", { name: new RegExp(business) });
  await expect(row).toBeVisible();
  await expect(row.getByText("active")).toBeVisible();
  await shot(page, "07-operator-console");
  await row.getByRole("button", { name: "Enter" }).click();
  await expect(page.getByTestId("acting-banner")).toContainText(business);
  await shot(page, "08-operator-inside-tenant");
  await page.getByRole("button", { name: "Exit to console" }).click();
  await page.waitForURL("**/operator");
  await expect(page.getByRole("row", { name: new RegExp(business) })).toBeVisible();
});
