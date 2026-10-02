import { strict as assert } from "node:assert";
import { test } from "node:test";
import { menuFor } from "../lib/menu.ts";

const hrefs = (role: string, extras: boolean) => menuFor(role, false, extras).map((l) => l.href);

test("the simple pilot exposes only the request-to-booking loop", () => {
  const expected = ["/inbox", "/approvals", "/schedule", "/settings"];
  assert.deepEqual(hrefs("owner", false), expected);
  assert.deepEqual(hrefs("staff", false), expected);
  assert.deepEqual(hrefs("viewer", false), expected);
});

test("extras do not add more top-level pilot pages", () => {
  assert.deepEqual(hrefs("owner", true), ["/inbox", "/approvals", "/schedule", "/settings"]);
});

test("the operator console shows only the businesses", () => {
  assert.deepEqual(menuFor("operator", true, true).map((l) => l.href), ["/operator"]);
});
