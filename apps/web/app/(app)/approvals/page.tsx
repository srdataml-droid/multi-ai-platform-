"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorLine, PageTitle } from "@/components/ui";
import { post } from "@/lib/api";
import { changed, editable, kindLabel, label, summarise, withEdits } from "@/lib/proposals";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { EXTRAS } from "@/lib/menu";

type Prediction = { p: number; level: "likely" | "unsure" | "unlikely"; reasons: string[]; data: "real" | "synthetic" };
type CustomerContext = {
  name: string | null;
  phone: string | null;
  email: string | null;
  channel: string;
  status: string;
  summary: string | null;
  intake: Record<string, unknown>;
};
type Proposal = { id: string; conversation_id: string | null; kind: string; params: Record<string, unknown>; risk: string; reason: string | null; created_at: string; prediction: Prediction | null; customer?: CustomerContext | null };
type Threshold = { threshold: number; would_auto_approve: number; of_which_staff_did_not_approve: number; precision: number | null; share_of_queue: number | null };
type Learning = {
  model: { data: string; trained_at: string; rows: number } | null;
  shadow: { decided_with_prediction: number; staff_approved: number; agreement: number | null; thresholds: Threshold[] };
};

const pct = (x: number | null | undefined) => (x == null ? "-" : `${Math.round(x * 100)}%`);

const intakeValue = (p: Proposal, ...keys: string[]) => {
  for (const key of keys) {
    const value = p.customer?.intake?.[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
};

function CustomerRequest({ p }: { p: Proposal }) {
  if (!p.customer) return null;
  const problem = intakeValue(p, "problem_type", "need", "service_type");
  const detail = intakeValue(p, "symptom", "concern", "notes");
  const location = intakeValue(p, "postcode", "address", "location");
  const urgency = intakeValue(p, "urgency");
  const preferred = intakeValue(p, "preferred_window", "preferred_time");
  const facts = [
    ["Problem", problem],
    ["Details", detail],
    ["Location", location],
    ["Urgency", urgency],
    ["Preferred", preferred],
  ].filter(([, value]) => value);

  return (
    <div className="mb-3 rounded-xl bg-white p-3 ring-1 ring-inset ring-slate-200" data-testid={`customer-${p.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-900">{p.customer.name || intakeValue(p, "name") || "Customer"}</div>
          <div className="text-xs text-slate-500">
            {[p.customer.phone, p.customer.email, p.customer.channel].filter(Boolean).join(" · ")}
          </div>
        </div>
        {p.conversation_id && <Link className="text-xs font-medium text-brand-700 hover:underline" href={`/conversations/${p.conversation_id}`}>Open conversation</Link>}
      </div>
      {facts.length > 0 && (
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          {facts.map(([labelText, value]) => (
            <div key={labelText} className="rounded-lg bg-slate-50 px-2.5 py-2">
              <dt className="text-xs text-slate-500">{labelText}</dt>
              <dd className="mt-0.5 text-slate-900">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {p.customer.summary && <p className="mt-2 text-xs text-slate-500">{p.customer.summary}</p>}
    </div>
  );
}


// The approval model's guess for one proposal. Advice only: staff still decide.
function Guess({ g }: { g: Prediction }) {
  const tone = g.level === "likely" ? "green" : g.level === "unlikely" ? "amber" : "slate";
  const words = g.level === "likely" ? "usually approved as written" : g.level === "unlikely" ? "often changed or rejected" : "could go either way";
  return (
    <p className="mb-2 text-xs text-slate-600" data-testid="prediction">
      <Badge tone={tone}>{pct(g.p)}</Badge> <span className="font-medium">Model&apos;s guess: {words}</span>
      {g.reasons.length > 0 && <span className="text-slate-500"> · {g.reasons.join(" · ")}</span>}
    </p>
  );
}

// What the model would have done if it were allowed to approve, against what staff did.
function LearningCard({ l }: { l: Learning }) {
  if (!l.model) return null;
  const s = l.shadow;
  return (
    <Card title="What the approval model has learnt">
      <p className="mb-2 text-xs text-slate-500">
        It learns from every Approve, Edit and Reject here. It never approves anything itself. Below: if it had been allowed to approve above a confidence level, how often would staff have agreed?
        {l.model.data === "synthetic" && " Demo model trained on synthetic data."}
      </p>
      {s.decided_with_prediction === 0 ? (
        <p className="text-sm text-slate-500">No decisions with a guess yet.</p>
      ) : (
        <>
          <p className="mb-2 text-sm">{s.decided_with_prediction} decisions compared; the guess matched staff {pct(s.agreement)} of the time.</p>
          <table className="w-full text-sm" data-testid="shadow-table">
            <thead><tr className="text-left text-xs text-slate-500"><th>Confidence</th><th>Would approve</th><th>Staff disagreed</th><th>Right</th></tr></thead>
            <tbody>
              {s.thresholds.map((t) => (
                <tr key={t.threshold}><td>{pct(t.threshold)}+</td><td>{t.would_auto_approve} ({pct(t.share_of_queue)})</td><td>{t.of_which_staff_did_not_approve}</td><td>{pct(t.precision)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}

export default function ApprovalsPage() {
  const { data, error, refresh } = usePoll<{ items: Proposal[] }>("/approvals", 4000);
  const { data: learning } = usePoll<Learning>("/approvals/learning", 60000);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<string, Record<string, string>>>({});
  const [err, setErr] = useState<string | null>(null);
  // Approved but could not be done: kept on screen so the person knows to follow up.
  const [failed, setFailed] = useState<Record<string, string>>({});

  const decide = async (p: Proposal, decision: "approve" | "reject" | "edit") => {
    setBusy(p.id);
    setErr(null);
    try {
      const body: Record<string, unknown> = { decision };
      if (decision === "edit") body.params = withEdits(p.params, editing[p.id] ?? {});
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

  const items = data?.items ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageTitle>Needs your decision{items.length > 0 && <span className="ml-2 text-base font-normal text-slate-600">{items.length}</span>}</PageTitle>
      <ErrorLine error={error ?? err} />
      {Object.entries(failed).map(([id, why]) => (
        <p key={id} data-testid="approval-failed" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800 ring-1 ring-inset ring-red-200">
          Approved, but it could not be done: {why}. The conversation is now with your team; open it from the inbox to follow up with the customer.
          <button className="ml-2 underline" onClick={() => setFailed((f) => { const n = { ...f }; delete n[id]; return n; })}>Dismiss</button>
        </p>
      ))}
      {data && !items.length && <Card><Empty>All clear. Novaxis has nothing waiting for you.</Empty></Card>}
      {items.map((p) => (
        <Card key={p.id} title={kindLabel(p.kind)} actions={<Badge tone={p.risk === "high" ? "red" : p.risk === "low" ? "slate" : "amber"}>{p.risk} risk</Badge>}>
          <p className="-mt-1 mb-3 text-xs text-slate-500">
            {p.reason && <>{p.reason.replace(/: default$/, "")} · </>}{ago(p.created_at)}
            {p.conversation_id && <> · <Link className="font-medium text-brand-700 hover:underline" href={`/conversations/${p.conversation_id}`}>open conversation</Link></>}
          </p>
          {EXTRAS && p.prediction && <Guess g={p.prediction} />}
          <CustomerRequest p={p} />
          <dl className="mb-3 grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1.5 rounded-xl bg-slate-50 p-3 text-sm" data-testid={`summary-${p.id}`}>
            {summarise(p.params).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="break-words text-slate-900">{v}</dd></div>
            ))}
          </dl>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => decide(p, "approve")} disabled={busy === p.id}>Approve</Button>
            <Button tone="danger" onClick={() => decide(p, "reject")} disabled={busy === p.id}>Decline</Button>
          </div>
          {editable(p.params).length > 0 && (
            <details className="mt-3 border-t border-slate-100 pt-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-600">Change before approving</summary>
              <div className="mt-3 flex flex-col gap-3">
                {editable(p.params).map((k) => (
                  <label key={k} className="flex flex-col gap-1 text-sm">
                    <span className="text-slate-500">{label(k)}</span>
                    <input data-testid={`edit-${p.id}-${k}`} value={editing[p.id]?.[k] ?? String(p.params[k] ?? "")} onChange={(e) => setEditing((s) => ({ ...s, [p.id]: { ...s[p.id], [k]: e.target.value } }))} />
                  </label>
                ))}
                <div><Button tone="secondary" onClick={() => decide(p, "edit")} disabled={busy === p.id || !changed(p.params, editing[p.id])}>Save changes and approve</Button></div>
              </div>
            </details>
          )}
        </Card>
      ))}
      {EXTRAS && learning && <LearningCard l={learning} />}
    </div>
  );
}
