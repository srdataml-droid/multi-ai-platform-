import assert from "node:assert/strict";
import { test } from "node:test";
import { getApiStatus } from "./api-status.ts";

const jsonResponse = (body: unknown) =>
  ({ ok: true, json: async () => body }) as unknown as Response;

test("reports reachable with health and version when both endpoints answer", async () => {
  const fake = (async (url: string) =>
    url.endsWith("/health")
      ? jsonResponse({ status: "ok" })
      : jsonResponse({ version: "0.0.0", commit: "abc" })) as unknown as typeof fetch;
  const s = await getApiStatus(fake);
  assert.deepEqual(s, { reachable: true, health: "ok", version: "0.0.0", commit: "abc" });
});

test("reports unreachable when fetch throws", async () => {
  const fake = (async () => {
    throw new Error("down");
  }) as unknown as typeof fetch;
  const s = await getApiStatus(fake);
  assert.deepEqual(s, { reachable: false });
});
