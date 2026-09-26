"use client";

import { Card, ErrorLine } from "@/components/ui";
import { usePoll } from "@/lib/usePoll";

type Analytics = { days: number; totals: Record<string, number>; series: ({ day: string; channel: string } & Record<string, number | string>)[] };
const LABELS: [string, string][] = [
  ["inbound", "Inbound messages"],
  ["answered_under_10s", "Answered under 10s"],
  ["intake_completed", "Intake completed"],
  ["bookings_proposed", "Bookings proposed"],
  ["bookings_approved", "Bookings approved"],
  ["escalations", "Escalations"],
  ["human_takeovers", "Human takeovers"],
];

export default function AnalyticsPage() {
  const { data, error } = usePoll<Analytics>("/analytics?days=30", 30000);
  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={error} />
      <Card title="Last 30 days">
        <div className="grid grid-cols-4 gap-3">
          {LABELS.map(([k, label]) => (
            <div key={k} className="rounded border border-slate-200 p-3">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="text-2xl font-semibold">{data?.totals[k] ?? 0}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-500">Rolled up hourly from the raw rows. Sensitive fields are never counted.</p>
      </Card>
      <Card title="By day and channel">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="py-1">Day</th><th>Channel</th>{LABELS.map(([k, l]) => <th key={k}>{l}</th>)}</tr></thead>
          <tbody>
            {(data?.series ?? []).map((r, i) => (
              <tr key={i} className="border-t border-slate-100"><td className="py-1">{r.day}</td><td>{r.channel}</td>{LABELS.map(([k]) => <td key={k}>{r[k]}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
