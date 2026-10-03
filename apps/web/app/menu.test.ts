import { strict as assert } from "node:assert";
import { test } from "node:test";
import { menuFor } from "../lib/menu.ts";

const hrefs = (role: string, extras: boolean) => menuFor(role, false, extras).map((l) => l.href);

test("the default pilot exposes only the request-to-booking loop", () => {
  const expected = ["/inbox", "/approvals", "/schedule", "/settings"];
  assert.deepEqual(hrefs("owner", false), expected);
  assert.deepEqual(hrefs("staff", false), expected);
  assert.deepEqual(hrefs("viewer", false), expected);
});

test("extras restore the parked full product without a second codebase", () => {
  assert.deepEqual(hrefs("owner", true), [
    "/inbox", "/approvals", "/schedule", "/contacts", "/settings",
    "/onboarding", "/billing", "/queue", "/analytics", "/stock",
  ]);
  assert.deepEqual(hrefs("staff", true), [
    "/inbox", "/approvals", "/schedule", "/contacts", "/settings",
    "/queue", "/analytics", "/stock",
  ]);
});

test("the operator console shows only the businesses", () => {
  assert.deepEqual(menuFor("operator", true, true).map((l) => l.href), ["/operator"]);
});
