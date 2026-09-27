"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { post } from "@/lib/api";
import { summarise } from "@/lib/proposals";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Proposal = { id: string; conversation_id: string | null; kind: string; params: Record<string, unknown>; risk: string; reason: string | null; created_at: string };

export default function ApprovalsPage() {
  const { data, error, refresh } = usePoll<{ items: Proposal[] }>("/approvals", 4000);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  // Approved but could not be done: kept on screen so the person knows to follow up.
  const [failed, setFailed] = useState<Record<string, string>>({});

  const decide = async (p: Proposal, decision: "approve" | "reject" | "edit") => {
    setBusy(p.id);
    setErr(null);
    try {
      const body: Record<string, unknown> = { decision };
      if (decision === "edit") body.params = JSON.parse(editing[p.id] ?? JSON.stringify(p.params));
      const r = await post<Record<string, unknown>>(`/approvals/${p.id}`, body);
      const done = (r.proposal ?? r) as { state?: string; error?: string | null };
      if (done.state === "failed") {
        setFailed((f) => ({ ...f, [p.id]: done.error ?? "unknown error" }));
      }
      setEditing((e) => { const n = { ...e }; delete n[p.id]; return n; });
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={error ?? err} />
      {Object.entries(failed).map(([id, why]) => (
        <p key={id} data-testid="approval-failed" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Approved, but it could not be done: {why}. The conversation is now with your team; open it from the inbox to follow up with the customer.
          <button className="ml-2 underline" onClick={() => setFailed((f) => { const n = { ...f }; delete n[id]; return n; })}>Dismiss</button>
        </p>
      ))}
      {data && !data.items.length && <Card title="Approvals"><p className="text-sm text-slate-500">Nothing waiting for a decision.</p></Card>}
      {(data?.items ?? []).map((p) => (
        <Card key={p.id} title={p.kind.replace(/_/g, " ")} actions={<Badge tone={p.risk === "high" ? "red" : "amber"}>{p.risk}</Badge>}>
          <p className="mb-2 text-xs text-slate-500">{p.reason} · {ago(p.created_at)} · {p.conversation_id && <Link className="text-blue-700 hover:underline" href={`/conversations/${p.conversation_id}`}>open conversation</Link>}</p>
          <dl className="mb-3 grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1 text-sm" data-testid={`summary-${p.id}`}>
            {summarise(p.params).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="break-words">{v}</dd></div>
            ))}
          </dl>
          <details className="mb-3">
            <summary className="cursor-pointer text-xs text-slate-500">Edit details before approving</summary>
            <textarea data-testid={`params-${p.id}`} className="mt-2 w-full rounded border border-slate-300 p-2 font-mono text-xs" rows={4} value={editing[p.id] ?? JSON.stringify(p.params, null, 2)} onChange={(e) => setEditing((s) => ({ ...s, [p.id]: e.target.value }))} />
          </details>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => decide(p, "approve")} disabled={busy === p.id}>Approve</Button>
            <Button tone="secondary" onClick={() => decide(p, "edit")} disabled={busy === p.id || !editing[p.id]}>Approve with edits</Button>
            <Button tone="danger" onClick={() => decide(p, "reject")} disabled={busy === p.id}>Reject</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
