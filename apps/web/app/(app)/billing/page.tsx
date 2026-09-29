"use client";

import { useEffect, useState } from "react";
import { TENANT_CHANGED } from "@/components/Nav";
import { Badge, Button, Card, ErrorLine, PageTitle, Stat } from "@/components/ui";
import { api, post } from "@/lib/api";
import { pounds } from "@/lib/money";

type Plan = { id: string; name: string; setup_pence: number; monthly_pence: number; included_messages: number; overage_pence: number; note: string };
type Billing = {
  provider: "demo" | "stripe";
  status: string;
  plan: string;
  subscribed: boolean;
  trial: { ends_at: string | null; days_left: number | null; replies_used: number; reply_cap: number; blocked: string | null } | null;
  period: { start: string; ai_replies: number; tokens: number; included: number | null; overage_replies: number; overage_pence: number };
  plans: Plan[];
  prices_are_placeholders: boolean;
};

const STATUS_TONE: Record<string, "green" | "amber" | "red" | "blue"> = { active: "green", trial: "blue", paused: "amber", closed: "red" };
const BLOCKED: Record<string, string> = {
  trial_expired: "Your trial has ended. The AI worker has stopped replying; conversations go to your team.",
  trial_cap_reached: "You have used every trial reply. The AI worker has stopped replying; conversations go to your team.",
};

export default function BillingPage() {
  const [b, setB] = useState<Billing | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = () => api<Billing>("/billing").then(setB).catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);
  if (!b) return <ErrorLine error={err} />;

  const choose = async (plan: string) => {
    setErr(null);
    try {
      const r = await post<{ url: string | null; outcome: string }>("/billing/checkout", { plan });
      if (r.url) window.location.href = r.url;
      else {
        setNote(`Demo billing: ${r.outcome}. No payment was taken.`);
        load();
        window.dispatchEvent(new Event(TENANT_CHANGED));
      }
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const t = b.trial;
  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <PageTitle>Billing</PageTitle>
      <ErrorLine error={err} />
      {note && <p className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{note}</p>}
      {b.provider === "demo" && (
        <p className="rounded-xl bg-brand-50 px-3 py-2 text-xs text-brand-900 ring-1 ring-inset ring-brand-100" data-testid="demo-billing">
          Demo billing: no money moves. Prices are placeholders.
        </p>
      )}
      <Card title="Your account">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone={STATUS_TONE[b.status] ?? "slate"}>{b.status}</Badge>
          <span>Plan: <strong className="capitalize">{b.plan}</strong></span>
        </div>
        {t && (
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-xs text-slate-600">
              <span>Trial: {t.replies_used} of {t.reply_cap} AI replies used</span>
              <span>{t.days_left !== null ? `${t.days_left} days left` : ""}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100"><div className="h-2 rounded-full bg-brand-600" style={{ width: `${Math.min(100, (100 * t.replies_used) / Math.max(1, t.reply_cap))}%` }} /></div>
            {t.blocked && <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">{BLOCKED[t.blocked] ?? t.blocked} Choose a plan below to switch it back on.</p>}
          </div>
        )}
        {b.status === "paused" && <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">A payment failed, so the AI worker is paused. It restarts as soon as the invoice is paid.</p>}
        {b.status === "closed" && <p className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">This account is closed. Contact Novaxis to reopen it.</p>}
      </Card>
      <Card title="This month">
        <div className="grid grid-cols-2 gap-4">
          <Stat value={b.period.ai_replies} label={`AI replies${b.period.included !== null ? ` of ${b.period.included}` : ""}`} />
          <Stat value={b.period.overage_replies} label={`over allowance · ${pounds(b.period.overage_pence)}`} />
        </div>
      </Card>
      {b.status !== "closed" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {b.plans.map((p) => (
            <Card key={p.id} title={p.name} actions={b.plan === p.id && b.subscribed ? <Badge tone="green">Current</Badge> : <Button onClick={() => choose(p.id)}>Choose {p.name}</Button>}>
              <div className="text-sm">
                <div className="text-2xl font-semibold tracking-tight">{pounds(p.monthly_pence)}<span className="text-sm font-normal text-slate-500"> / month</span></div>
                <div className="mt-1 text-slate-600">{p.setup_pence ? `${pounds(p.setup_pence)} setup` : "No setup fee"}</div>
                <div className="mt-1 text-slate-600">{p.included_messages.toLocaleString("en-GB")} AI replies included, then {pounds(p.overage_pence)} each</div>
                <p className="mt-2 text-xs text-slate-500">{p.note}</p>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
