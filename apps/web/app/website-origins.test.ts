import { strict as assert } from "node:assert";
import { test } from "node:test";
import { websiteOrigins } from "../lib/website-origins.ts";

test("website addresses become exact origins, preserve www and local ports, and deduplicate", () => {
  assert.deepEqual(websiteOrigins("example.com/contact\nhttps://www.example.com/book,https://example.com/\nhttp://localhost:5599/test"), ["https://example.com", "https://www.example.com", "http://localhost:5599"]);
});

test("non-web protocols, malformed URLs, and embedded credentials are refused", () => {
  for (const input of ["ftp://example.com", "https://user:password@example.com", "https://", "https://bad host/"]) {
    assert.throws(() => websiteOrigins(input));
  }
  assert.deepEqual(websiteOrigins(""), []);
});
