"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { api, post, put } from "@/lib/api";
import { every } from "@/lib/every";
import { when } from "@/lib/format";

export type Ticket = { id: string; ref: string; action: "create" | "update" | "cancel"; starts_at: string; ends_at: string; summary: string; status: string; service_name: string; customer_name: string; customer_phone: string; created_at: string; entered_at: string | null };
type Settings = { vendor_name: string; email_to: string | null; date_order: "dmy" | "mdy"; service_map: Record<string, string> };
export type Bridge = {
  connected: boolean;
  settings?: Settings;
  health?: { ok: boolean; detail: string };
  last_import_at?: string | null;
  last_import_report?: { rows: number; imported: number; skipped: number; errors: string[] } | null;
  vendor_busy_upcoming?: number;
  services: { code: string; name: string }[];
  tickets: Ticket[];
};

const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";

// Settings card: connect a booking system that has no API, and upload its diary export.
export function BookingBridgeCard({ onChange }: { onChange?: () => void }) {
  const [b, setB] = useState<Bridge | null>(null);
  const [form, setForm] = useState<Settings>({ vendor_name: "", email_to: "", date_order: "dmy", service_map: {} });
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = () =>
    api<Bridge>("/integrations/bridge")
      .then((d) => {
        setB(d);
        if (d.settings) setForm({ ...d.settings, email_to: d.settings.email_to ?? "" });
      })
      .catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);
  if (!b) return <ErrorLine error={err} />;

  const save = async () => {
    setErr(null);
    try {
      await put("/integrations/bridge", { ...form, email_to: form.email_to || null });
      setNote("Saved.");
      await load();
      onChange?.();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const upload = async (file: File) => {
    setErr(null);
    try {
      const r = await post<{ rows: number; imported: number; skipped: number; errors: string[]; conflicts: number }>("/integrations/bridge/import", { csv: await file.text() });
      setNote(`Imported ${r.imported} of ${r.rows} rows${r.skipped ? `, skipped ${r.skipped}` : ""}${r.conflicts ? `. ${r.conflicts} clash(es) with our bookings: the customers were offered new times` : ""}.`);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <Card title="Booking software without an API (bridge)" actions={<Button onClick={save}>{b.connected ? "Save" : "Connect"}</Button>}>
      <ErrorLine error={err} />
      {note && <p className="mb-2 rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{note}</p>}
      <p className="mb-3 text-xs text-slate-500">
        For diaries we cannot write to. Approved bookings become hand-offs for the office to key in; a daily diary export (CSV) stops double booking.
      </p>
      {b.connected && b.health && (
        <p className="mb-3 text-sm">
          <Badge tone={b.health.ok ? "green" : "amber"}>{b.health.ok ? "healthy" : "needs attention"}</Badge> <span className="text-slate-600">{b.health.detail}</span>
          {b.vendor_busy_upcoming !== undefined && <span className="text-slate-500"> · {b.vendor_busy_upcoming} upcoming busy times</span>}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm">Software name<input className={input} placeholder="e.g. your job management system" value={form.vendor_name} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })} /></label>
        <label className="text-sm">Office email for hand-offs<input className={input} placeholder="office@yourbusiness.co.uk" value={form.email_to ?? ""} onChange={(e) => setForm({ ...form, email_to: e.target.value })} /></label>
        <label className="text-sm">Dates in the export
          <select className={input} value={form.date_order} onChange={(e) => setForm({ ...form, date_order: e.target.value as "dmy" | "mdy" })}>
            <option value="dmy">Day first (30/09/2026)</option>
            <option value="mdy">Month first (09/30/2026)</option>
          </select>
        </label>
      </div>
      {b.services.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-slate-500">Job type to pick in {form.vendor_name || "your software"} for each service</div>
          <div className="mt-1 grid gap-2 sm:grid-cols-2">
            {b.services.map((s) => (
              <label key={s.code} className="flex items-center gap-2 text-sm">
                <span className="w-40 shrink-0">{s.name}</span>
                <input className="w-full rounded border border-slate-300 px-2 py-1 text-sm" placeholder={s.name} value={form.service_map[s.code] ?? ""} onChange={(e) => setForm({ ...form, service_map: { ...form.service_map, [s.code]: e.target.value } })} />
              </label>
            ))}
          </div>
        </div>
      )}
      {b.connected && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 text-sm">
          <label className="cursor-pointer rounded border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-50">
            Upload today&apos;s diary export (CSV)
            <input type="file" accept=".csv,text/csv" className="hidden" data-testid="bridge-upload" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          {b.last_import_at && <span className="text-xs text-slate-500">Last import {when(b.last_import_at)}</span>}
          <button className="ml-auto text-xs text-red-600" onClick={() => api("/integrations/bridge", { method: "DELETE" }).then(load)}>Disconnect</button>
        </div>
      )}
    </Card>
  );
}

// Schedule card: the hand-offs the office still has to key in.
export function HandoffsCard() {
  const [b, setB] = useState<Bridge | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api<Bridge>("/integrations/bridge").then(setB).catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
    return every(load, 10000);
  }, []);
  if (!b || (!b.connected && !b.tickets.length)) return <ErrorLine error={err} />;
  const open = b.tickets.filter((t) => t.status !== "entered");
  const vendor = b.settings?.vendor_name ?? "your booking software";
  const entered = async (id: string) => {
    try {
      await post(`/integrations/bridge/tickets/${id}/entered`);
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const tone = { create: "green", update: "blue", cancel: "red" } as const;
  return (
    <Card title={`To key into ${vendor} (${open.length})`}>
      <ErrorLine error={err} />
      {!open.length ? (
        <p className="text-sm text-slate-500">Nothing waiting. Every booking is in {vendor}.</p>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm" data-testid="handoffs">
          {open.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="flex items-center gap-2">
                <Badge tone={tone[t.action]}>{t.action === "create" ? "new" : t.action === "update" ? "moved" : "cancelled"}</Badge>
                <code className="text-xs">{t.ref}</code>
                <span>{when(t.starts_at)}</span>
                <span className="text-slate-600">{t.service_name} · {t.customer_name} {t.customer_phone}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-slate-500">{t.status === "emailed" ? "emailed to office" : t.status === "not_emailed" ? "not emailed" : "sending"}</span>
                <button className="rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white" onClick={() => entered(t.id)}>Entered</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
