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

// What the worker wants to do, in words, so an owner can decide without reading JSON.
export function summarise(params: Record<string, unknown>): [string, string][] {
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== "" && typeof v !== "object")
    .map(([k, v]) => [LABELS[k] ?? k.replace(/_/g, " "), String(v)]);
}
