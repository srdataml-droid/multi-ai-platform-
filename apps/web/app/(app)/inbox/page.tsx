"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Card, Empty, ErrorLine, PageTitle } from "@/components/ui";
import { STATUS_LABEL, ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Row = { id: string; channel: string; status: string; bucket: string; unread: number; awaiting: number; contact: { display_name: string | null }; last_message: { body: string; direction: string; at: string } | null; columns: Record<string, string | null>; updated_at: string };
type Inbox = { columns: { key: string; label: string }[]; items: Row[] };

const needsYou = (r: Row) => r.status === "waiting_human" || r.awaiting > 0;

export default function InboxPage() {
  const { data, error } = usePoll<Inbox>("/inbox");
  const [only, setOnly] = useState(false);
  const rows = (data?.items ?? []).filter((r) => !only || needsYou(r));
  const waiting = (data?.items ?? []).filter(needsYou).length;
  // The name column is the heading of each row; the others become small facts under it.
  const facts = (data?.columns ?? []).filter((c) => c.key !== "name");

  return (
    <>
      <PageTitle
        actions={
          <div role="tablist" className="flex rounded-lg bg-slate-200/60 p-0.5 text-xs font-medium">
            {[["All", false], [`Needs you${waiting ? ` · ${waiting}` : ""}`, true]].map(([text, v]) => (
              <button key={String(v)} role="tab" aria-selected={only === v} onClick={() => setOnly(v as boolean)} className={`rounded-md px-3 py-1.5 ${only === v ? "bg-white text-slate-900 shadow-sm" : "text-slate-600"}`}>{text}</button>
            ))}
          </div>
        }
      >
        Inbox
      </PageTitle>
      <ErrorLine error={error} />
      <Card>
        {data && !rows.length ? (
          <Empty>{only ? "Nothing needs you right now." : "No conversations yet."}</Empty>
        ) : (
          <ul className="-mx-4 -my-4 divide-y divide-slate-100 sm:-mx-5 sm:-my-5">
            {rows.map((r) => {
              const name = r.contact.display_name ?? r.columns.name ?? "New visitor";
              const shown = facts.filter((c) => r.columns[c.key]);
              return (
                <li key={r.id}>
                  <Link href={`/conversations/${r.id}`} className="flex gap-3 px-4 py-3.5 hover:bg-slate-50 sm:px-5">
                    <span aria-hidden="true" className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold uppercase ${needsYou(r) ? "bg-amber-100 text-amber-800" : "bg-brand-50 text-brand-700"}`}>{name.charAt(0)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-2">
                        <span className={`truncate text-sm ${r.unread ? "font-semibold text-slate-900" : "font-medium text-slate-800"}`}>{name}</span>
                        <span className="shrink-0 text-xs text-slate-500">{ago(r.updated_at)}</span>
                      </span>
                      <span className={`mt-0.5 line-clamp-2 text-sm ${r.unread ? "text-slate-900" : "text-slate-500"}`}>
                        {r.last_message?.body ?? ""}
                      </span>
                      <span className="mt-2 flex flex-wrap items-center gap-1.5">
                        {r.status === "waiting_human" ? <Badge tone="red">Needs a person</Badge> : r.awaiting ? <Badge tone="amber">{r.awaiting} to approve</Badge> : <Badge>{STATUS_LABEL[r.status] ?? r.status}</Badge>}
                        {shown.map((c, i) => (
                          <span key={c.key} className={`${i > 1 ? "hidden sm:inline" : ""} rounded-md bg-slate-50 px-1.5 py-0.5 text-xs text-slate-600 ring-1 ring-inset ring-slate-200`}><span className="text-slate-500">{c.label}:</span> {r.columns[c.key]}</span>
                        ))}
                        <span className="text-xs text-slate-500">{r.channel}</span>
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
