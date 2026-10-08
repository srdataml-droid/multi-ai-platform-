import { strict as assert } from "node:assert";
import { test } from "node:test";
import { menuFor } from "../lib/menu.ts";

const hrefs = (role: string, extras: boolean) => menuFor(role, false, extras).map((l) => l.href);

test("the prototype menu is the core loop; parked pages stay out", () => {
  assert.deepEqual(hrefs("owner", false), ["/inbox", "/approvals", "/schedule", "/contacts", "/settings", "/assistant", "/onboarding", "/billing"]);
  assert.deepEqual(hrefs("staff", false), ["/inbox", "/approvals", "/schedule", "/contacts", "/settings"]);
});

test("a deployment with extras switched on shows the parked pages again", () => {
  for (const page of ["/queue", "/analytics", "/stock"]) assert.ok(hrefs("owner", true).includes(page));
});

test("the operator console shows only the businesses", () => {
  assert.deepEqual(menuFor("operator", true, true).map((l) => l.href), ["/operator"]);
});
