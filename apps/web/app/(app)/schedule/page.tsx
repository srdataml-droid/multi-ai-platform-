"use client";

import Link from "next/link";
import { useState } from "react";
import { HandoffsCard } from "@/components/BookingBridge";
import { Badge, Card, Empty, ErrorLine, PageTitle } from "@/components/ui";
import { post } from "@/lib/api";
import { clock, day } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { EXTRAS } from "@/lib/menu";

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
    const d = day(a.starts_at);
    byDay.set(d, [...(byDay.get(d) ?? []), a]);
  }
  const today = day(new Date().toISOString());
  const small = "rounded-lg px-2.5 py-1 text-xs font-medium ring-1 ring-inset ring-slate-300 hover:bg-slate-50";
  return (
    <div className="flex flex-col gap-4">
      <PageTitle>Schedule</PageTitle>
      <ErrorLine error={error ?? err} />
      <HandoffsCard />
      {data && !data.items.length && <Card><Empty>No bookings in the next 30 days.</Empty></Card>}
      {[...byDay.entries()].map(([d, items]) => (
        <Card key={d} title={<>{d === today ? "Today" : d}<span className="ml-2 font-normal text-slate-500">{items.length}</span></>}>
          <ul className="-mx-1 flex flex-col gap-1">
            {items.map((a) => {
              const past = new Date(a.starts_at).getTime() <= now;
              return (
                <li key={a.id} data-testid="appointment" className={`flex gap-3 rounded-xl px-1 py-2`}>
                  <div className="w-14 shrink-0 pt-0.5 text-right">
                    <div className="text-sm font-semibold tabular-nums text-slate-900">{clock(a.starts_at)}</div>
                    <div className="text-xs tabular-nums text-slate-500">{clock(a.ends_at)}</div>
                  </div>
                  <div className={`w-1 shrink-0 rounded-full ${a.status === "confirmed" ? "bg-emerald-400" : a.status === "held" ? "bg-amber-400" : "bg-slate-300"}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-sm font-medium text-slate-900">{a.service_name}</span>
                      <Badge tone={a.status === "confirmed" ? "green" : a.status === "held" ? "amber" : "slate"}>{a.status}</Badge>
                      {a.customer_confirmed_at && <Badge tone="green">customer confirmed</Badge>}
                      {EXTRAS && !past && a.risk && (
                        <span title={a.risk.reasons.join("; ")} data-testid="no-show-risk">
                          <Badge tone={riskTone[a.risk.level]}>no-show risk {Math.round(a.risk.score * 100)}%</Badge>
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-slate-500">
                      <span className="truncate">{a.contact.display_name ?? "New visitor"}</span>
                      {a.external_ref && <span className="text-xs text-slate-500">{a.external_ref.split(":")[0]}</span>}
                      {a.conversation_id && <Link className="text-xs font-medium text-brand-700 hover:underline" href={`/conversations/${a.conversation_id}`}>conversation</Link>}
                    </div>
                    {past && a.status === "confirmed" && (a.outcome ? (
                      <div className="mt-2 flex items-center gap-2 text-xs">
                        <Badge tone={a.outcome === "attended" ? "green" : "red"}>{a.outcome === "attended" ? "came" : "no-show"}</Badge>
                        <button className="text-slate-500 underline" onClick={() => record(a, null)}>undo</button>
                      </div>
                    ) : (
                      <div className="mt-2 flex items-center gap-2 text-xs" data-testid="record-outcome">
                        <span className="text-slate-500">Did they come?</span>
                        <button className={small} onClick={() => record(a, "attended")}>Came</button>
                        <button className={small} onClick={() => record(a, "no_show")}>No-show</button>
                      </div>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      ))}
    </div>
  );
}
