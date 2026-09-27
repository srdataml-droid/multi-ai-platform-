// Repeat `fn` every `ms` while the page is visible. A hidden tab (another tab, a locked
// phone) makes no requests; when it becomes visible again it refreshes at once instead of
// waiting out the interval. Returns a function that stops it.
type Visibility = Pick<Document, "hidden" | "addEventListener" | "removeEventListener">;

export function every(fn: () => void, ms: number, doc: Visibility | undefined = globalThis.document): () => void {
  const id = setInterval(() => {
    if (!doc?.hidden) fn();
  }, ms);
  const onVisible = () => {
    if (!doc?.hidden) fn();
  };
  doc?.addEventListener("visibilitychange", onVisible);
  return () => {
    clearInterval(id);
    doc?.removeEventListener("visibilitychange", onVisible);
  };
}
