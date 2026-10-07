"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorLine, PageTitle } from "@/components/ui";
import { post, put } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

type Callback = { id: string; name: string; phone: string; email: string; details: string; intake: { postcode: string; service: string }; window: string; state: string; outcome: string | null };

export default function Callbacks() {
  const { data, error, refresh } = usePoll<{ items: Callback[] }>("/callbacks");
  const cfg = usePoll<{ enabled: boolean; slug: string; can_configure: boolean }>("/callbacks/config");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [windows, setWindows] = useState<Record<string, string>>({});
  const act = async (fn: () => Promise<unknown>) => { setErr(null); setBusy(true); try { await fn(); refresh(); cfg.refresh(); } catch(e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return <>
    <PageTitle actions={<Link href="/schedule" className="text-sm text-brand-700">Back to schedule</Link>}>Callback requests</PageTitle>
    <p className="mb-5 text-sm text-slate-600">Persistent requests for your team. Approval creates a manual callback task; no call, message or calendar event is sent.</p>
    <ErrorLine error={err || error || cfg.error} />
    {cfg.data && <div className="mb-5"><Card title="Website enquiry form">
      <div className="flex flex-wrap items-center gap-3"><Badge tone={cfg.data.enabled ? "green" : "slate"}>{cfg.data.enabled ? "Accepting enquiries" : "Disabled"}</Badge>
      {cfg.data.can_configure && <Button tone="secondary" disabled={busy} onClick={() => act(() => put("/callbacks/config", { enabled: !cfg.data!.enabled }))}>{cfg.data.enabled ? "Disable form" : "Enable form"}</Button>}
      {cfg.data.enabled && <Link className="text-sm text-brand-700 underline" href={`/enquire/${encodeURIComponent(cfg.data.slug)}`}>Open customer form</Link>}</div>
      <p className="mt-3 text-xs text-slate-500">Share the customer form address after checking it in a signed-out browser. Your hosting provider may still protect preview links.</p>
    </Card></div>}
    <div className="space-y-4">{data?.items.length === 0 && <Card><Empty>No callback requests yet.</Empty></Card>}
      {data?.items.map(c => <Card key={c.id} title={c.name} actions={<Badge tone={c.state === "awaiting" ? "amber" : c.state === "executed" ? "green" : "slate"}>{c.outcome || c.state}</Badge>}>
        <p className="mb-2 text-sm text-slate-500">{c.intake.service} · {c.intake.postcode}</p>
        <p className="mb-4 whitespace-pre-wrap text-sm leading-6">{c.details}</p>
        <p className="mb-4 break-all text-sm">{c.phone} · {c.email}</p>
        {c.state === "awaiting" ? <>
          <label className="mb-4 grid gap-2 text-sm font-medium">Callback window<input maxLength={160} value={windows[c.id] ?? c.window} onChange={e => setWindows({ ...windows, [c.id]: e.target.value })} /></label>
          <div className="flex flex-wrap gap-2"><Button disabled={busy || !(windows[c.id] ?? c.window).trim()} onClick={() => act(() => post(`/approvals/${c.id}`, windows[c.id] !== undefined && windows[c.id] !== c.window ? { decision: "edit", params: { window: windows[c.id] } } : { decision: "approve" }))}>Approve callback</Button><Button disabled={busy} tone="danger" onClick={() => act(() => post(`/approvals/${c.id}`, { decision: "reject" }))}>Decline</Button></div>
        </> : <p className="text-sm font-medium">{c.window}</p>}
        {c.outcome === "scheduled" && <div className="mt-4 flex flex-wrap gap-2">{[["completed", "Mark completed"], ["no_answer", "No answer"], ["cancelled", "Cancel callback"]].map(([outcome, label]) => <Button key={outcome} disabled={busy} tone="secondary" onClick={() => act(() => post(`/callbacks/${c.id}/outcome`, { outcome }))}>{label}</Button>)}</div>}
      </Card>)}
    </div>
    <p className="mt-5 text-xs text-slate-500">Most recent 100 requests. Outcomes are recorded once; no automated follow-up is sent.</p>
  </>;
}
