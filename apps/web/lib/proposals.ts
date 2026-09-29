const LABELS: Record<string, string> = {
  service_code: "Service",
  preferred_window: "When",
  notes: "Notes",
  text: "Message",
  reason: "Reason",
  summary: "Summary",
  appointment_id: "Appointment",
  new_window: "New time",
};

export const label = (k: string): string => LABELS[k] ?? k.replace(/_/g, " ");

// What the worker wants to do, in words, so an owner can decide without reading JSON.
export function summarise(params: Record<string, unknown>): [string, string][] {
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== "" && typeof v !== "object")
    .map(([k, v]) => [label(k), String(v)]);
}

// Details a person may change before approving: words and numbers. Ids and codes stay as
// the system set them, so an edit cannot point a booking at the wrong record.
const FIXED = (k: string) => k.endsWith("_id") || k.endsWith("_code");

export function editable(params: Record<string, unknown>): string[] {
  return Object.entries(params)
    .filter(([k, v]) => !FIXED(k) && (typeof v === "string" || typeof v === "number"))
    .map(([k]) => k);
}

// The proposal with the person's changes, each value kept in its original type.
export function withEdits(params: Record<string, unknown>, edits: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...params };
  for (const [k, v] of Object.entries(edits)) {
    if (!editable(params).includes(k)) continue;
    out[k] = typeof params[k] === "number" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v;
  }
  return out;
}

export function changed(params: Record<string, unknown>, edits: Record<string, string> | undefined): boolean {
  if (!edits) return false;
  return Object.entries(edits).some(([k, v]) => editable(params).includes(k) && String(params[k] ?? "") !== v);
}
