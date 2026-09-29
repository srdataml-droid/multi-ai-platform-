"use client";

import { Card, ErrorLine, PageTitle, Stat } from "@/components/ui";
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
      <PageTitle>Analytics <span className="text-base font-normal text-slate-600">30 days</span></PageTitle>
      <ErrorLine error={error} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {LABELS.map(([k, label]) => (
          <div key={k} className="rounded-2xl border border-slate-200/80 bg-white p-4">
            <Stat value={data?.totals[k] ?? 0} label={label} />
          </div>
        ))}
      </div>
      <Card title="By day and channel">
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-500"><th className="py-1 pr-3">Day</th><th>Channel</th>{LABELS.map(([k, l]) => <th key={k} className="pr-3 font-medium">{l}</th>)}</tr></thead>
          <tbody>
            {(data?.series ?? []).map((r, i) => (
              <tr key={i} className="border-t border-slate-100"><td className="py-1">{r.day}</td><td>{r.channel}</td>{LABELS.map(([k]) => <td key={k}>{r[k]}</td>)}</tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>
    </div>
  );
}
