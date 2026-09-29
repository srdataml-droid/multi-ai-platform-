import { expect, test } from "@playwright/test";

// A business sets up its own booking types in Settings, starting from the trade's standard
// questions, and they are there after a reload.

test("the owner starts a booking type from the standard questions and saves it", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("email").fill("owner@demo-restoration.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/inbox");
  await page.goto("/settings");
  await expect(page.getByText("Different customers, different questions")).toBeVisible();

  await page.getByRole("button", { name: "Start from our standard questions" }).click();
  const first = page.getByTestId("booking-type-0");
  await expect(first).toBeVisible();
  await expect(first.getByLabel("Question").first()).not.toHaveValue("");
  await page.getByTestId("type-name-0").fill("Water damage survey");
  await page.getByRole("button", { name: "Save all" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("type-name-0")).toHaveValue("Water damage survey");

  // Leave the demo business as it was.
  await page.getByRole("button", { name: "Remove this booking type" }).click();
  await page.getByRole("button", { name: "Save all" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("booking-type-0")).toHaveCount(0);
});
