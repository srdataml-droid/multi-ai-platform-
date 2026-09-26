"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { post } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Proposal = { id: string; conversation_id: string | null; kind: string; params: Record<string, unknown>; risk: string; reason: string | null; created_at: string };

export default function ApprovalsPage() {
  const { data, error, refresh } = usePoll<{ items: Proposal[] }>("/approvals", 4000);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  const decide = async (p: Proposal, decision: "approve" | "reject" | "edit") => {
    setBusy(p.id);
    setErr(null);
    try {
      const body: Record<string, unknown> = { decision };
      if (decision === "edit") body.params = JSON.parse(editing[p.id] ?? JSON.stringify(p.params));
      await post(`/approvals/${p.id}`, body);
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
      {data && !data.items.length && <Card title="Approvals"><p className="text-sm text-slate-500">Nothing waiting for a decision.</p></Card>}
      {(data?.items ?? []).map((p) => (
        <Card key={p.id} title={p.kind.replace(/_/g, " ")} actions={<Badge tone={p.risk === "high" ? "red" : "amber"}>{p.risk}</Badge>}>
          <p className="mb-2 text-xs text-slate-500">{p.reason} · {ago(p.created_at)} · {p.conversation_id && <Link className="text-blue-700 hover:underline" href={`/conversations/${p.conversation_id}`}>open conversation</Link>}</p>
          <textarea data-testid={`params-${p.id}`} className="mb-3 w-full rounded border border-slate-300 p-2 font-mono text-xs" rows={4} value={editing[p.id] ?? JSON.stringify(p.params, null, 2)} onChange={(e) => setEditing((s) => ({ ...s, [p.id]: e.target.value }))} />
          <div className="flex gap-2">
            <Button onClick={() => decide(p, "approve")} disabled={busy === p.id}>Approve</Button>
            <Button tone="secondary" onClick={() => decide(p, "edit")} disabled={busy === p.id || !editing[p.id]}>Approve with edits</Button>
            <Button tone="danger" onClick={() => decide(p, "reject")} disabled={busy === p.id}>Reject</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
