import { strict as assert } from "node:assert";
import { test } from "node:test";
import { clock, day, setBusinessTimeZone, when } from "../lib/format.ts";

test("times show in the business's zone, whatever the viewer's device says", () => {
  const winterMorning = "2026-11-04T10:00:00Z"; // 10:00 in London; 11:00 in Lagos
  setBusinessTimeZone("Europe/London");
  assert.match(when(winterMorning), /10:00/);
  setBusinessTimeZone("Africa/Lagos");
  assert.match(when(winterMorning), /11:00/);
  setBusinessTimeZone(undefined);
});

test("a booking belongs to the business's day, whatever the viewer's device says", () => {
  const lateLondon = "2026-11-04T23:30:00Z"; // Wednesday 23:30 in London; Thursday 00:30 in Lagos
  assert.equal(day(lateLondon, "Europe/London"), "Wednesday 4 November");
  assert.equal(day(lateLondon, "Africa/Lagos"), "Thursday 5 November");
  assert.equal(clock(lateLondon, "Africa/Lagos"), "00:30");
});
