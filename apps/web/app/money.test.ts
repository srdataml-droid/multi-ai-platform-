import { strict as assert } from "node:assert";
import { test } from "node:test";
import { pounds } from "../lib/money.ts";

test("pounds formats whole and fractional amounts", () => {
  assert.equal(pounds(30000), "£300");
  assert.equal(pounds(20), "£0.20");
  assert.equal(pounds(150050), "£1,500.50");
});
