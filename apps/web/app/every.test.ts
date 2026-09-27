import { strict as assert } from "node:assert";
import { test } from "node:test";
import { every } from "../lib/every.ts";

function fakeDoc() {
  const listeners = new Set<() => void>();
  return {
    hidden: false,
    addEventListener: (_: string, f: () => void) => listeners.add(f),
    removeEventListener: (_: string, f: () => void) => listeners.delete(f),
    show() {
      this.hidden = false;
      listeners.forEach((f) => f());
    },
    listeners,
  };
}

test("a hidden tab stops polling and refreshes as soon as it is shown again", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDoc();
  let calls = 0;
  const stop = every(() => calls++, 1000, doc as unknown as Document);
  t.mock.timers.tick(3000);
  assert.equal(calls, 3);
  doc.hidden = true;
  t.mock.timers.tick(10_000);
  assert.equal(calls, 3, "no requests while hidden");
  doc.show();
  assert.equal(calls, 4, "refreshes on return");
  stop();
  t.mock.timers.tick(5000);
  assert.equal(calls, 4);
  assert.equal(doc.listeners.size, 0);
});
