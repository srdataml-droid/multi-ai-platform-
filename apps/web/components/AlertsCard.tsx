"use client";

import { useEffect, useState } from "react";
import { TENANT_CHANGED } from "@/components/Nav";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { api, post } from "@/lib/api";
import { type AlertStatus, pushSupported, turnOffAlerts, turnOnAlerts } from "@/lib/push";

// Settings card: how the team hears about approvals, emergencies and hand-overs.
export function AlertsCard() {
  const [a, setA] = useState<AlertStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = () => api<AlertStatus>("/alerts").then(setA).catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);
  if (!a) return <ErrorLine error={err} />;
  const changed = (s: AlertStatus) => {
    setA(s);
    window.dispatchEvent(new Event(TENANT_CHANGED));
  };
  const on = async () => {
    setErr(null);
    try {
      changed(await turnOnAlerts(a.public_key ?? ""));
      setNote("Alerts are on for this device.");
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const off = async () => {
    try {
      changed(await turnOffAlerts());
      setNote("Alerts are off for this device.");
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const test = async () => {
    setErr(null);
    try {
      const r = await post<{ delivered: number }>("/alerts/test");
      setNote(`Test sent to ${r.delivered} device${r.delivered === 1 ? "" : "s"}.`);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const c = a.channels;
  return (
    <Card title="Alerts for your team" actions={a.alerts_off ? <Badge tone="red">off</Badge> : <Badge tone="green">on</Badge>}>
      <ErrorLine error={err} />
      {note && <p className="mb-2 rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{note}</p>}
      <p className="mb-3 text-sm text-slate-600">
        You are told when an approval is waiting, a customer is handed to your team, or a customer reports an emergency.
      </p>
      <ul className="mb-3 space-y-1 text-sm">
        <li>Phone and computer alerts: <strong>{c.push_devices}</strong> device{c.push_devices === 1 ? "" : "s"}</li>
        <li>Email: {c.email ? "connected" : "not connected"}</li>
        <li>Text messages: {c.sms ? "connected" : "not connected"}</li>
      </ul>
      {!c.push_available ? (
        <p className="text-xs text-slate-500">Device alerts are not switched on for this deployment yet.</p>
      ) : !a.can_subscribe ? (
        <p className="text-xs text-slate-500">Only owners and staff receive alerts.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {a.this_user_subscribed ? (
            <>
              <Button onClick={test}>Send a test alert</Button>
              <Button tone="secondary" onClick={off}>Turn off on this device</Button>
            </>
          ) : (
            <Button onClick={on} disabled={!pushSupported()}>Turn on alerts on this device</Button>
          )}
        </div>
      )}
      {!pushSupported() && <p className="mt-2 text-xs text-slate-500">This browser cannot receive alerts. On iPhone, open the dashboard in Safari, choose Share, then Add to Home Screen, and turn alerts on from there.</p>}
    </Card>
  );
}
