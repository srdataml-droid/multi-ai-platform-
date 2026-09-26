import { strict as assert } from "node:assert";
import { test } from "node:test";
import { summarise } from "../lib/proposals.ts";

test("proposal params read as labelled plain text, skipping empties and nested values", () => {
  assert.deepEqual(
    summarise({ service_code: "repair_visit", preferred_window: "next week", notes: "", extra: { a: 1 }, new_field: 3 }),
    [["Service", "repair_visit"], ["When", "next week"], ["new field", "3"]],
  );
});
