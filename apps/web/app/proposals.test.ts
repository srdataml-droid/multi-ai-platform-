import { strict as assert } from "node:assert";
import { test } from "node:test";
import { changed, editable, summarise, withEdits } from "../lib/proposals.ts";
import { keyFor } from "../lib/bookingTypes.ts";

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

test("answer keys come from the question, unique, never the reserved one", () => {
  assert.equal(keyFor("What's your name?", []), "what_s_your_name");
  assert.equal(keyFor("What's your name?", ["what_s_your_name"]), "what_s_your_name_2");
  assert.equal(keyFor("2nd phone?", []), "q_2nd_phone");
  assert.equal(keyFor("Booking type", []), "booking_type_answer");
  assert.equal(keyFor("???", []), "answer");
});
