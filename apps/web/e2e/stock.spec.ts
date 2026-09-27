import path from "node:path";
import { expect, test } from "@playwright/test";

// Stock counting in the browser: photo in, count and dots out, staff confirm. The demo
// business uses the synthetic-shelf model shipped in the repo; the fixture shelf holds 39 items.
test("staff count a shelf from a photo and confirm the count", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("email").fill("owner@demo-hvac.test");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/inbox");

  await page.getByRole("link", { name: "Stock" }).click();
  await page.getByTestId("stock-product").fill("Cola 330ml");
  await page.getByTestId("stock-photo").setInputFiles(path.join(__dirname, "fixtures", "shelf.jpg"));
  await page.getByRole("button", { name: "Count" }).click();

  const result = page.getByTestId("stock-result");
  await expect(result).toContainText("Counted", { timeout: 15_000 });
  await expect(result).toContainText("demo model");
  const counted = Number(await result.locator("strong").innerText());
  expect(Math.abs(counted - 39)).toBeLessThanOrEqual(3);
  await expect(page.locator("svg circle").first()).toBeVisible();

  await page.getByTestId("stock-truth").fill("39");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(result).toContainText("saved: 39");
  await expect(page.getByText("confirmed 39").first()).toBeVisible();
});
