"use client";

import Link from "next/link";
import { useState } from "react";
import { HandoffsCard } from "@/components/BookingBridge";
import { Badge, Card, ErrorLine } from "@/components/ui";
import { post } from "@/lib/api";
import { when } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Risk = { score: number; level: "low" | "medium" | "high"; reasons: string[] };
type Appt = { id: string; starts_at: string; ends_at: string; service_code: string; service_name: string; customer_confirmed_at: string | null; status: string; outcome: "attended" | "no_show" | null; risk: Risk | null; external_ref: string | null; contact: { display_name: string | null }; conversation_id: string | null };

const riskTone = { low: "slate", medium: "amber", high: "red" } as const;

export default function SchedulePage() {
  // A week back, so staff can say who turned up (the labels the no-show model learns from).
  const { data, error, refresh } = usePoll<{ items: Appt[] }>("/appointments?days=30&back=7", 10000);
  const [err, setErr] = useState<string | null>(null);
  const now = Date.now();

  const record = async (a: Appt, outcome: Appt["outcome"]) => {
    setErr(null);
    try {
      await post(`/appointments/${a.id}/outcome`, { outcome });
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const byDay = new Map<string, Appt[]>();
  for (const a of data?.items ?? []) {
    const day = new Date(a.starts_at).toDateString();
    byDay.set(day, [...(byDay.get(day) ?? []), a]);
  }
  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={error ?? err} />
      <HandoffsCard />
      {data && !data.items.length && <Card title="Schedule"><p className="text-sm text-slate-500">No appointments in the next 30 days.</p></Card>}
      {[...byDay.entries()].map(([day, items]) => (
        <Card key={day} title={day}>
          <ul className="divide-y divide-slate-100 text-sm">
            {items.map((a) => {
              const past = new Date(a.starts_at).getTime() <= now;
              return (
                <li key={a.id} data-testid="appointment" className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    {when(a.starts_at)} · {a.service_name} · {a.contact.display_name ?? "Unknown"}
                    {a.customer_confirmed_at && <span className="ml-2 text-xs text-emerald-700">customer confirmed</span>}
                    {!past && a.risk && (
                      <span className="ml-2" title={a.risk.reasons.join("; ")} data-testid="no-show-risk">
                        <Badge tone={riskTone[a.risk.level]}>no-show risk {Math.round(a.risk.score * 100)}%</Badge>
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-2">
                    {a.external_ref && <span className="text-xs text-slate-400">{a.external_ref.split(":")[0]}</span>}
                    <Badge tone={a.status === "confirmed" ? "green" : a.status === "held" ? "amber" : "slate"}>{a.status}</Badge>
                    {past && a.status === "confirmed" && (a.outcome ? (
                      <span className="flex items-center gap-1 text-xs">
                        <Badge tone={a.outcome === "attended" ? "green" : "red"}>{a.outcome === "attended" ? "came" : "no-show"}</Badge>
                        <button className="text-slate-500 underline" onClick={() => record(a, null)}>undo</button>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs" data-testid="record-outcome">
                        <span className="text-slate-500">Did they come?</span>
                        <button className="rounded border border-slate-300 px-2 py-0.5" onClick={() => record(a, "attended")}>Came</button>
                        <button className="rounded border border-slate-300 px-2 py-0.5" onClick={() => record(a, "no_show")}>No-show</button>
                      </span>
                    ))}
                    {a.conversation_id && <Link className="text-xs text-blue-700 hover:underline" href={`/conversations/${a.conversation_id}`}>conversation</Link>}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      ))}
    </div>
  );
}
