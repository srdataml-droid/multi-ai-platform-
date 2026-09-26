"use client";

import Link from "next/link";
import { Badge, Card, ErrorLine } from "@/components/ui";
import { when } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Appt = { id: string; starts_at: string; ends_at: string; service_code: string; status: string; external_ref: string | null; contact: { display_name: string | null }; conversation_id: string | null };

export default function SchedulePage() {
  const { data, error } = usePoll<{ items: Appt[] }>("/appointments?days=30", 10000);
  const byDay = new Map<string, Appt[]>();
  for (const a of data?.items ?? []) {
    const day = new Date(a.starts_at).toDateString();
    byDay.set(day, [...(byDay.get(day) ?? []), a]);
  }
  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={error} />
      {data && !data.items.length && <Card title="Schedule"><p className="text-sm text-slate-500">No appointments in the next 30 days.</p></Card>}
      {[...byDay.entries()].map(([day, items]) => (
        <Card key={day} title={day}>
          <ul className="divide-y divide-slate-100 text-sm">
            {items.map((a) => (
              <li key={a.id} data-testid="appointment" className="flex items-center justify-between py-2">
                <span>{when(a.starts_at)} · {a.service_code} · {a.contact.display_name ?? "Unknown"}</span>
                <span className="flex items-center gap-2">
                  {a.external_ref && <span className="text-xs text-slate-400">{a.external_ref.split(":")[0]}</span>}
                  <Badge tone={a.status === "confirmed" ? "green" : a.status === "held" ? "amber" : "slate"}>{a.status}</Badge>
                  {a.conversation_id && <Link className="text-xs text-blue-700 hover:underline" href={`/conversations/${a.conversation_id}`}>conversation</Link>}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
