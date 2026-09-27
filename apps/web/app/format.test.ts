import { strict as assert } from "node:assert";
import { test } from "node:test";
import { setBusinessTimeZone, when } from "../lib/format.ts";

test("times show in the business's zone, whatever the viewer's device says", () => {
  const winterMorning = "2026-11-04T10:00:00Z"; // 10:00 in London; 11:00 in Lagos
  setBusinessTimeZone("Europe/London");
  assert.match(when(winterMorning), /10:00/);
  setBusinessTimeZone("Africa/Lagos");
  assert.match(when(winterMorning), /11:00/);
  setBusinessTimeZone(undefined);
});
