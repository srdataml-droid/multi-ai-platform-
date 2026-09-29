import { strict as assert } from "node:assert";
import { test } from "node:test";
import { changed, editable, summarise, withEdits } from "../lib/proposals.ts";

test("proposal params read as labelled plain text, skipping empties and nested values", () => {
  assert.deepEqual(
    summarise({ service_code: "repair_visit", preferred_window: "next week", notes: "", extra: { a: 1 }, new_field: 3 }),
    [["Service", "repair_visit"], ["When", "next week"], ["new field", "3"]],
  );
});

test("staff can change words and numbers, never ids or codes", () => {
  const p = { appointment_id: "a1", service_code: "repair_visit", preferred_window: "Thursday", notes: "", visits: 2, extra: { a: 1 } };
  assert.deepEqual(editable(p), ["preferred_window", "notes", "visits"]);
  assert.deepEqual(
    withEdits(p, { preferred_window: "Friday afternoon", visits: "3", appointment_id: "evil", service_code: "x" }),
    { ...p, preferred_window: "Friday afternoon", visits: 3 },
  );
  assert.equal(changed(p, undefined), false);
  assert.equal(changed(p, { preferred_window: "Thursday" }), false, "typed back the same");
  assert.equal(changed(p, { preferred_window: "Friday" }), true);
  assert.equal(changed(p, { appointment_id: "evil" }), false);
});
