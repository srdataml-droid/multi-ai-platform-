"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine, PageTitle, Stat, Table } from "@/components/ui";
import { api, post } from "@/lib/api";
import { enterTenant } from "@/lib/auth";
import { ago } from "@/lib/format";

type Row = {
  id: string;
  name: string;
  slug: string;
  pack_id: string;
  status: string;
  plan: string;
  created_at: string;
  trial_ends_at: string | null;
  ai_replies_this_month: number;
  waiting_human: number;
  last_inbound_at: string | null;
  health: "ok" | "attention";
  problems: string[];
};

const EVENTS: [string, string][] = [
  ["checkout.session.completed", "Payment succeeded"],
  ["invoice.payment_failed", "Payment failed"],
  ["invoice.paid", "Invoice paid"],
  ["customer.subscription.deleted", "Subscription cancelled"],
];
const STATUS_TONE: Record<string, "green" | "amber" | "red" | "blue"> = { active: "green", trial: "blue", paused: "amber", closed: "red" };

export default function OperatorPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [provider, setProvider] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = () =>
    api<{ items: Row[]; billing_provider: string }>("/operator/tenants")
      .then((d) => {
        setRows(d.items);
        setProvider(d.billing_provider);
      })
      .catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);

  const enter = async (r: Row) => {
    try {
      const d = await post<{ token: string }>(`/operator/tenants/${r.id}/enter`);
      enterTenant(d.token);
      router.replace("/inbox");
      window.location.reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const simulate = async (r: Row, event: string) => {
    if (!event) return;
    try {
      const d = await post<{ outcome: string }>(`/operator/tenants/${r.id}/billing-event`, { event });
      setNote(`${r.name}: ${d.outcome}`);
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const attention = rows.filter((r) => r.health === "attention").length;
  return (
    <div className="flex flex-col gap-4">
      <PageTitle>Tenants</PageTitle>
      <ErrorLine error={err} />
      {note && <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{note}</p>}
      <div className="grid grid-cols-3 gap-3">
        <Card><Stat value={rows.length} label="businesses" /></Card>
        <Card><Stat value={rows.filter((r) => r.status === "trial").length} label="on trial" /></Card>
        <Card><Stat value={attention} label="need attention" tone={attention ? "amber" : undefined} /></Card>
      </div>
      <Card title="All businesses" actions={<Button tone="secondary" onClick={load}>Refresh</Button>}>
        <Table<Row>
          rows={rows}
          empty="No customer tenants yet."
          columns={[
            { key: "name", label: "Business", render: (r) => <div><div className="font-medium">{r.name}</div><div className="text-xs text-slate-500">{r.slug} · {r.pack_id}</div></div> },
            { key: "status", label: "Status", render: (r) => <div className="flex flex-col gap-1"><Badge tone={STATUS_TONE[r.status] ?? "slate"}>{r.status}</Badge><span className="text-xs capitalize text-slate-500">{r.plan}</span></div> },
            { key: "usage", label: "AI replies (month)", render: (r) => r.ai_replies_this_month },
            { key: "waiting", label: "Waiting on staff", render: (r) => r.waiting_human },
            { key: "last", label: "Last message in", render: (r) => (r.last_inbound_at ? ago(r.last_inbound_at) : "never") },
            { key: "health", label: "Health", render: (r) => r.health === "ok" ? <Badge tone="green">ok</Badge> : <div className="flex flex-col gap-1">{r.problems.map((p) => <Badge key={p} tone="amber">{p}</Badge>)}</div> },
            {
              key: "actions",
              label: "",
              render: (r) => (
                <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-end">
                  <Button onClick={() => enter(r)}>Enter</Button>
                  {provider === "demo" && (
                    <select aria-label="Simulate billing event" className="rounded border border-slate-300 px-1 py-1 text-xs" value="" onChange={(e) => simulate(r, e.target.value)}>
                      <option value="">Simulate billing…</option>
                      {EVENTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  )}
                </div>
              ),
            },
          ]}
        />
        <p className="mt-3 text-xs text-slate-500">Entering lasts one hour and is written to that business&apos;s audit log.</p>
      </Card>
    </div>
  );
}
