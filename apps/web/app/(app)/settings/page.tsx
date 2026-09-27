"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { AlertsCard } from "@/components/AlertsCard";
import { BookingBridgeCard } from "@/components/BookingBridge";
import { api, post, put } from "@/lib/api";

type Settings = { tenant: { name: string; slug: string; pack_id: string; worker_enabled: boolean }; settings: Record<string, unknown> & { business_hours: Record<string, { open: string; close: string }>; services: { code: string; name: string; duration_minutes: number; auto_confirm: boolean }[]; service_area: string[]; risk_overrides: Record<string, string>; channels: Record<string, { enabled: boolean; config: Record<string, string> }> }; risk_floors: Record<string, { default: string; floor: string; description: string }> };
type Staff = { id: string; email: string; role: string };
type Integration = { id: string; provider: string; health: string };
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const RISKS = ["low", "medium", "high"];

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [integ, setInteg] = useState<{ items: Integration[]; system_of_record: string | null } | null>(null);
  const [snippet, setSnippet] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [newStaff, setNewStaff] = useState({ email: "", role: "staff" });

  const load = () => {
    api<Settings>("/settings").then(setS).catch((e: Error) => setErr(e.message));
    api<{ items: Staff[] }>("/settings/staff").then((d) => setStaff(d.items)).catch(() => null);
    api<{ items: Integration[]; system_of_record: string | null }>("/integrations").then(setInteg).catch(() => null);
    api<{ snippet: string }>("/settings/widget").then((d) => setSnippet(d.snippet)).catch(() => null);
  };
  useEffect(load, []);
  if (!s) return <ErrorLine error={err} />;
  const st = s.settings;
  const update = (patch: Partial<typeof st>) => setS({ ...s, settings: { ...st, ...patch } });
  const save = async () => {
    setErr(null);
    setSaved(false);
    try {
      const r = await put<Settings>("/settings", { settings: st, name: s.tenant.name, worker_enabled: s.tenant.worker_enabled });
      setS(r);
      setSaved(true);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const connectGoogle = async () => {
    try {
      const r = await api<{ url: string }>("/integrations/google/connect");
      window.location.href = r.url;
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <ErrorLine error={err} />
      {saved && <p className="rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-700">Saved.</p>}
      <Card title="Business" actions={<Button onClick={save}>Save all</Button>}>
        <label className="block text-sm">Name<input className="mt-1 w-full rounded border border-slate-300 px-2 py-1" value={s.tenant.name} onChange={(e) => setS({ ...s, tenant: { ...s.tenant, name: e.target.value } })} /></label>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={s.tenant.worker_enabled} onChange={(e) => setS({ ...s, tenant: { ...s.tenant, worker_enabled: e.target.checked } })} /> Worker enabled (untick to stop all automated replies now)</label>
      </Card>
      <Card title="Opening hours">
        <div className="grid grid-cols-7 gap-2 text-sm">
          {DAYS.map((d) => {
            const h = st.business_hours[d];
            return (
              <div key={d} className="rounded border border-slate-200 p-2">
                <label className="flex items-center gap-1 font-medium"><input type="checkbox" checked={!!h} onChange={(e) => { const bh = { ...st.business_hours }; if (e.target.checked) bh[d] = { open: "09:00", close: "17:00" }; else delete bh[d]; update({ business_hours: bh }); }} />{d}</label>
                {h && <>
                  <input className="mt-1 w-full rounded border px-1" value={h.open} onChange={(e) => update({ business_hours: { ...st.business_hours, [d]: { ...h, open: e.target.value } } })} />
                  <input className="mt-1 w-full rounded border px-1" value={h.close} onChange={(e) => update({ business_hours: { ...st.business_hours, [d]: { ...h, close: e.target.value } } })} />
                </>}
              </div>
            );
          })}
        </div>
      </Card>
      <Card title="Services">
        <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase text-slate-500"><th>Code</th><th>Name</th><th>Minutes</th><th>Auto-confirm</th><th></th></tr></thead>
          <tbody>{st.services.map((svc, i) => (
            <tr key={i} className="border-t border-slate-100">
              <td><input className="w-full rounded border px-1" value={svc.code} onChange={(e) => { const v = [...st.services]; v[i] = { ...svc, code: e.target.value }; update({ services: v }); }} /></td>
              <td><input className="w-full rounded border px-1" value={svc.name} onChange={(e) => { const v = [...st.services]; v[i] = { ...svc, name: e.target.value }; update({ services: v }); }} /></td>
              <td><input className="w-20 rounded border px-1" type="number" value={svc.duration_minutes} onChange={(e) => { const v = [...st.services]; v[i] = { ...svc, duration_minutes: Number(e.target.value) }; update({ services: v }); }} /></td>
              <td><input type="checkbox" checked={svc.auto_confirm} onChange={(e) => { const v = [...st.services]; v[i] = { ...svc, auto_confirm: e.target.checked }; update({ services: v }); }} /></td>
              <td><button className="text-xs text-red-600" onClick={() => update({ services: st.services.filter((_, j) => j !== i) })}>remove</button></td>
            </tr>
          ))}</tbody></table>
        <Button tone="secondary" onClick={() => update({ services: [...st.services, { code: "new_service", name: "New service", duration_minutes: 60, auto_confirm: false }] })}>Add service</Button>
      </Card>
      <Card title="Service area (postcode or ZIP prefixes, comma separated)">
        <input className="w-full rounded border border-slate-300 px-2 py-1 text-sm" value={st.service_area.join(", ")} onChange={(e) => update({ service_area: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
      </Card>
      <Card title="What the worker may do on its own">
        <p className="mb-2 text-xs text-slate-500">Low runs immediately. Medium waits for your approval. High is always refused. You cannot go below the floor.</p>
        <table className="w-full text-sm"><tbody>
          {Object.entries(s.risk_floors).map(([kind, f]) => (
            <tr key={kind} className="border-t border-slate-100">
              <td className="py-1 pr-2">{kind.replace(/_/g, " ")}<div className="text-xs text-slate-500">{f.description}</div></td>
              <td className="w-40">
                <select className="rounded border px-1" value={st.risk_overrides[kind] ?? f.default} onChange={(e) => update({ risk_overrides: { ...st.risk_overrides, [kind]: e.target.value } })}>
                  {RISKS.filter((r) => RISKS.indexOf(r) >= RISKS.indexOf(f.floor)).map((r) => <option key={r} value={r}>{r}{r === f.default ? " (default)" : ""}</option>)}
                </select>
              </td>
            </tr>
          ))}
        </tbody></table>
      </Card>
      <Card title="Channels">
        <ul className="text-sm">{Object.entries(st.channels).map(([k, c]) => <li key={k} className="flex justify-between border-t border-slate-100 py-1"><span>{k}</span><span>{c.enabled ? <Badge tone="green">enabled</Badge> : <Badge>off</Badge>} <span className="text-xs text-slate-500">{Object.values(c.config).join(" · ")}</span></span></li>)}</ul>
      </Card>
      <Card title="Calendar and integrations" actions={<Button tone="secondary" onClick={connectGoogle}>Connect Google Calendar</Button>}>
        <p className="text-sm">System of record: <strong>{integ?.system_of_record ?? "…"}</strong></p>
        <ul className="mt-2 text-sm">{(integ?.items ?? []).map((i) => <li key={i.id} className="flex justify-between border-t border-slate-100 py-1"><span>{i.provider}</span><span className="flex gap-2"><Badge tone={i.health === "connected" ? "green" : "slate"}>{i.health}</Badge>{i.health === "connected" && <button className="text-xs text-red-600" onClick={() => post(`/integrations/${i.id}/disconnect`).then(load)}>disconnect</button>}</span></li>)}</ul>
      </Card>
      <AlertsCard />
      <BookingBridgeCard onChange={load} />
      <Card title="Staff">
        <ul className="text-sm">{staff.map((u) => <li key={u.id} className="flex justify-between border-t border-slate-100 py-1"><span>{u.email}</span>
          <select className="rounded border px-1" value={u.role} onChange={(e) => put(`/settings/staff/${u.id}`, { role: e.target.value }).then(load).catch((er: Error) => setErr(er.message))}>{["owner", "staff", "viewer"].map((r) => <option key={r}>{r}</option>)}</select></li>)}</ul>
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); post("/settings/staff", newStaff).then(() => { setNewStaff({ email: "", role: "staff" }); load(); }).catch((er: Error) => setErr(er.message)); }}>
          <input className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm" placeholder="email" value={newStaff.email} onChange={(e) => setNewStaff({ ...newStaff, email: e.target.value })} />
          <select className="rounded border px-1 text-sm" value={newStaff.role} onChange={(e) => setNewStaff({ ...newStaff, role: e.target.value })}>{["owner", "staff", "viewer"].map((r) => <option key={r}>{r}</option>)}</select>
          <Button type="submit" tone="secondary">Add</Button>
        </form>
      </Card>
      <Card title="Website chat widget">
        <p className="mb-2 text-xs text-slate-500">Paste this one line before the closing body tag of your website.</p>
        <pre data-testid="widget-snippet" className="overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{snippet}</pre>
        <label className="mt-3 block text-sm">Websites allowed to show your chat (comma separated)
          <input data-testid="widget-origins" className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" placeholder="https://www.yourbusiness.co.uk" value={((st.widget_origins as string[] | undefined) ?? []).join(", ")} onChange={(e) => update({ widget_origins: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
        </label>
        <p className="mt-1 text-xs text-slate-500">
          {((st.widget_origins as string[] | undefined) ?? []).length ? "Only these websites can use your chat box." : "Empty: any website could copy your chat box. Add your own website address to stop that."} Press Save all at the top.
        </p>
      </Card>
    </div>
  );
}
