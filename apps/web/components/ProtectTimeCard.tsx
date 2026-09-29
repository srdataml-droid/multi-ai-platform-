"use client";

import { Button, Card } from "@/components/ui";

export type Protected = { label: string; days: string[]; start: string; end: string };
export type BookingRules = {
  min_notice_minutes: number;
  buffer_minutes: number;
  max_per_day: number | null;
  protected: Protected[];
};

// The server's defaults (tenant_settings.BookingRules), for a business saved before the
// rules existed.
export const NO_RULES: BookingRules = { min_notice_minutes: 30, buffer_minutes: 0, max_per_day: null, protected: [] };

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

// Free on the calendar is not the same as available. These rules decide which times the
// assistant may offer customers; saved with "Save all".
export function ProtectTimeCard({ rules, onChange }: { rules: BookingRules; onChange: (r: BookingRules) => void }) {
  const set = (patch: Partial<BookingRules>) => onChange({ ...rules, ...patch });
  const setBlock = (i: number, patch: Partial<Protected>) =>
    set({ protected: rules.protected.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const num = (v: string) => (v.trim() === "" ? null : Math.max(0, Number(v)));

  return (
    <Card title="Protect your time">
      <p className="mb-3 text-sm text-slate-600">
        The assistant only offers times these rules allow.
      </p>
      <div className="grid gap-3 text-sm sm:grid-cols-3">
        <label>
          <span className="text-slate-500">Shortest notice for a booking (hours)</span>
          <input data-testid="rule-notice" type="number" min={0} step={0.5} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" value={rules.min_notice_minutes / 60} onChange={(e) => set({ min_notice_minutes: Math.round((num(e.target.value) ?? 0) * 60) })} />
        </label>
        <label>
          <span className="text-slate-500">Gap kept around other bookings (minutes)</span>
          <input data-testid="rule-buffer" type="number" min={0} step={5} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" value={rules.buffer_minutes} onChange={(e) => set({ buffer_minutes: num(e.target.value) ?? 0 })} />
        </label>
        <label>
          <span className="text-slate-500">Most bookings in a day (empty: no limit)</span>
          <input data-testid="rule-max" type="number" min={1} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" value={rules.max_per_day ?? ""} onChange={(e) => set({ max_per_day: num(e.target.value) || null })} />
        </label>
      </div>

      <p className="mb-2 mt-4 text-sm font-medium">Times nobody can book</p>
      <p className="mb-2 text-xs text-slate-500">Lunch, school runs, meetings: kept free even when the diary is empty.</p>
      {rules.protected.map((p, i) => (
        <div key={i} className="mb-2 flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2 text-sm" data-testid={`protected-${i}`}>
          <input aria-label="What it is" className="w-36 rounded border px-1" value={p.label} onChange={(e) => setBlock(i, { label: e.target.value })} />
          {DAYS.map((d) => (
            <label key={d} className="flex items-center gap-0.5">
              <input type="checkbox" checked={p.days.includes(d)} onChange={(e) => setBlock(i, { days: e.target.checked ? [...p.days, d] : p.days.filter((x) => x !== d) })} />
              {d}
            </label>
          ))}
          <input aria-label="From" type="time" className="rounded border px-1" value={p.start} onChange={(e) => setBlock(i, { start: e.target.value })} />
          <span>to</span>
          <input aria-label="Until" type="time" className="rounded border px-1" value={p.end} onChange={(e) => setBlock(i, { end: e.target.value })} />
          <button className="text-xs text-red-600" onClick={() => set({ protected: rules.protected.filter((_, j) => j !== i) })}>remove</button>
        </div>
      ))}
      <Button tone="secondary" onClick={() => set({ protected: [...rules.protected, { label: "Lunch", days: ["mon", "tue", "wed", "thu", "fri"], start: "12:00", end: "13:00" }] })}>
        Protect a time
      </Button>
    </Card>
  );
}
