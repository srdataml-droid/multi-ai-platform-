"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { fetchAuthConfig } from "@/lib/auth";
import { AlertsCard } from "@/components/AlertsCard";
import { BookingBridgeCard } from "@/components/BookingBridge";
import { AgentKeysCard } from "@/components/AgentKeysCard";
import { NO_RULES, ProtectTimeCard, type BookingRules } from "@/components/ProtectTimeCard";
import { BookingTypesCard, type BookingType } from "@/components/BookingTypesCard";
import { FaqCard, type Faq } from "@/components/FaqCard";
import { api, post, put } from "@/lib/api";
import { EXTRAS, SIMPLE_PILOT } from "@/lib/menu";

type Settings = { tenant: { name: string; slug: string; pack_id: string; worker_enabled: boolean }; settings: Record<string, unknown> & { business_hours: Record<string, { open: string; close: string }>; services: { code: string; name: string; duration_minutes: number; auto_confirm: boolean }[]; service_area: string[]; risk_overrides: Record<string, string>; channels: Record<string, { enabled: boolean; config: Record<string, string> }> }; risk_floors: Record<string, { default: string; floor: string; description: string }> };
type Staff = { id: string; email: string; role: string };
type Integration = { id: string; provider: string; health: string };
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_NAME: Record<string, string> = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
const ROLE_NAME: Record<string, string> = { owner: "Owner", staff: "Team", viewer: "View only" };
const SECTIONS: [string, string][] = SIMPLE_PILOT
  ? [["business", "Business"], ["hours", "Hours"], ["services", "Services"], ["area", "Area"], ["calendar", "Calendar"], ["widget", "Website chat"]]
  : [["business", "Business"], ["hours", "Hours"], ["services", "Services"], ["answers", "Answers"], ["types", "Booking types"], ["channels", "Channels"], ["team", "Team"], ["widget", "Website chat"], ["data", "Customer data"]];
const RISKS = ["low", "medium", "high"];

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [integ, setInteg] = useState<{ items: Integration[]; system_of_record: string | null } | null>(null);
  const [snippet, setSnippet] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [newStaff, setNewStaff] = useState({ email: "", role: "staff" });
  // Hosted with sign-in codes: each person added gets one, shown here once to pass on.
  const [codes, setCodes] = useState(false);
  const [issued, setIssued] = useState<{ email: string; code: string } | null>(null);
  useEffect(() => {
    fetchAuthConfig().then((c) => setCodes(c.mode === "demo")).catch(() => null);
  }, []);
  const addStaff = async () => {
    setErr(null);
    try {
      const r = await post<{ email: string; login_code: string | null }>("/settings/staff", newStaff);
      if (r.login_code) setIssued({ email: r.email, code: r.login_code });
      setNewStaff({ email: "", role: "staff" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const newCode = async (u: Staff) => {
    if (!confirm(`Give ${u.email} a new sign-in code? Their old code stops working.`)) return;
    setErr(null);
    try {
      const r = await post<{ login_code: string }>(`/settings/staff/${u.id}/code`);
      setIssued({ email: u.email, code: r.login_code });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

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
      // A question-and-answer row left empty is dropped rather than refused.
      const faqs = ((st.faqs as { question: string; answer: string }[] | undefined) ?? []).filter((f) => f.question.trim() && f.answer.trim());
      const r = await put<Settings>("/settings", { settings: { ...st, faqs }, name: s.tenant.name, worker_enabled: s.tenant.worker_enabled });
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
      <div className="sticky top-[57px] z-10 -mx-4 border-b border-slate-200/80 bg-[#f6f7fb]/95 px-4 pb-2 pt-1 backdrop-blur md:top-0 md:-mx-8 md:px-8 md:pt-3">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
          <div className="flex items-center gap-3">
            {saved && <span className="text-sm font-medium text-emerald-700">Saved.</span>}
            <Button onClick={save}>Save all</Button>
          </div>
        </div>
        <nav aria-label="Sections" className="-mx-1 mt-2 flex gap-1 overflow-x-auto pb-1 text-xs font-medium [scrollbar-width:none]">
          {SECTIONS.map(([id, name]) => <a key={id} href={`#${id}`} className="shrink-0 rounded-full bg-white px-3 py-1.5 text-slate-600 ring-1 ring-inset ring-slate-200 hover:text-slate-900">{name}</a>)}
        </nav>
      </div>
      <ErrorLine error={err} />
      {SIMPLE_PILOT && (
        <p className="rounded-xl bg-brand-50 px-3 py-2 text-sm text-brand-900 ring-1 ring-inset ring-brand-100">
          Simple pilot: only the controls needed for customer request → approval → booking are shown. The larger Novaxis features are still in the codebase for later.
        </p>
      )}
      <Card id="business" title="Business">
        <label className="flex flex-col gap-1 text-sm">Name<input value={s.tenant.name} onChange={(e) => setS({ ...s, tenant: { ...s.tenant, name: e.target.value } })} /></label>
        <label className="mt-4 flex items-start gap-2 text-sm"><input className="mt-0.5" type="checkbox" checked={s.tenant.worker_enabled} onChange={(e) => setS({ ...s, tenant: { ...s.tenant, worker_enabled: e.target.checked } })} /><span>Assistant on<span className="block text-xs text-slate-500">Untick to stop all automatic replies now.</span></span></label>
      </Card>
      <Card id="hours" title="Opening hours">
        <div className="grid max-w-2xl gap-2">
          {DAYS.map((d) => {
            const h = st.business_hours[d];
            return (
              <div key={d} className={`grid grid-cols-[4.25rem_1fr_1fr] items-center gap-2 rounded-xl border px-2.5 py-2 text-sm sm:grid-cols-[8rem_1fr_1fr] sm:px-3 ${h ? "border-slate-200" : "border-dashed border-slate-200 text-slate-500"}`}>
                <label className="flex items-center gap-2 font-medium"><input type="checkbox" checked={!!h} onChange={(e) => { const bh = { ...st.business_hours }; if (e.target.checked) bh[d] = { open: "09:00", close: "17:00" }; else delete bh[d]; update({ business_hours: bh }); }} /><span className="sm:hidden">{DAY_NAME[d].slice(0, 3)}</span><span className="hidden sm:inline">{DAY_NAME[d]}</span></label>
                {h ? <>
                  <input type="time" aria-label={`${DAY_NAME[d]} opens`} className="w-full min-w-0 !px-2" value={h.open} onChange={(e) => update({ business_hours: { ...st.business_hours, [d]: { ...h, open: e.target.value } } })} />
                  <input type="time" aria-label={`${DAY_NAME[d]} closes`} className="w-full min-w-0 !px-2" value={h.close} onChange={(e) => update({ business_hours: { ...st.business_hours, [d]: { ...h, close: e.target.value } } })} />
                </> : <span className="col-span-2 text-xs">Closed</span>}
              </div>
            );
          })}
        </div>
      </Card>
      {!SIMPLE_PILOT && <ProtectTimeCard rules={{ ...NO_RULES, ...(st.booking_rules as Partial<BookingRules> | undefined) }} onChange={(r) => update({ booking_rules: r })} />}
      <Card id="services" title="Services" actions={<Button tone="secondary" onClick={() => update({ services: [...st.services, { code: "new_service", name: "New service", duration_minutes: 60, auto_confirm: false }] })}>Add service</Button>}>
        <div className="flex flex-col gap-2">
          {st.services.map((svc, i) => {
            const set = (patch: Partial<typeof svc>) => { const v = [...st.services]; v[i] = { ...svc, ...patch }; update({ services: v }); };
            return (
              <div key={i} className="grid grid-cols-2 items-end gap-2 rounded-xl border border-slate-200 p-3 text-sm md:grid-cols-[2fr_1.3fr_6rem_auto_auto] md:border-0 md:p-0">
                <label className="col-span-2 flex flex-col gap-1 md:col-span-1"><span className="text-xs text-slate-500">Name</span><input value={svc.name} onChange={(e) => set({ name: e.target.value })} /></label>
                <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">Code</span><input value={svc.code} onChange={(e) => set({ code: e.target.value })} /></label>
                <label className="flex flex-col gap-1"><span className="text-xs text-slate-500">Minutes</span><input type="number" value={svc.duration_minutes} onChange={(e) => set({ duration_minutes: Number(e.target.value) })} /></label>
                {!SIMPLE_PILOT && <label className="flex items-center gap-2 py-2"><input type="checkbox" checked={svc.auto_confirm} onChange={(e) => set({ auto_confirm: e.target.checked })} />Auto-confirm</label>}
                <button className="justify-self-end py-2 text-xs font-medium text-red-600" onClick={() => update({ services: st.services.filter((_, j) => j !== i) })}>Remove</button>
              </div>
            );
          })}
        </div>
      </Card>
      {!SIMPLE_PILOT && (
        <>
          <div id="answers" className="scroll-mt-32" />
          <FaqCard faqs={(st.faqs as Faq[] | undefined) ?? []} onChange={(f) => update({ faqs: f })} />
          <div id="types" className="scroll-mt-32" />
          <BookingTypesCard
            types={(st.booking_types as BookingType[] | undefined) ?? []}
            services={st.services}
            starter={(s as unknown as { starter_booking_type?: BookingType }).starter_booking_type ?? null}
            question={(st.booking_type_question as string | undefined) ?? "What can we help you with?"}
            onChange={(t) => update({ booking_types: t })}
            onQuestion={(q) => update({ booking_type_question: q })}
          />
        </>
      )}
      <Card id="area" title="Service area">
        <input aria-label="Postcode or ZIP prefixes, comma separated" placeholder="SW1, SE1, E1" className="w-full" value={st.service_area.join(", ")} onChange={(e) => update({ service_area: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
      </Card>
      {!SIMPLE_PILOT && (
              <Card title="What the worker may do on its own">
                <p className="mb-2 text-xs text-slate-500">Low: runs now. Medium: waits for you. High: never.</p>
                <table className="w-full text-sm"><tbody>
                  {Object.entries(s.risk_floors).map(([kind, f]) => (
                    <tr key={kind} className="border-t border-slate-100">
                      <td className="py-2 pr-2 first-letter:uppercase">{kind.replace(/_/g, " ")}<div className="text-xs text-slate-500">{f.description}</div></td>
                      <td className="w-40">
                        <select aria-label={kind.replace(/_/g, " ")} value={st.risk_overrides[kind] ?? f.default} onChange={(e) => update({ risk_overrides: { ...st.risk_overrides, [kind]: e.target.value } })}>
                          {RISKS.filter((r) => RISKS.indexOf(r) >= RISKS.indexOf(f.floor)).map((r) => <option key={r} value={r}>{r}{r === f.default ? " (default)" : ""}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody></table>
              </Card>
      )}
      {!SIMPLE_PILOT && (
        <>
                <Card id="channels" title="Channels">
                  <ul className="text-sm">{Object.entries(st.channels).map(([k, c]) => <li key={k} className="flex justify-between border-t border-slate-100 py-1"><span>{k}</span><span>{c.enabled ? <Badge tone="green">enabled</Badge> : <Badge>off</Badge>} <span className="text-xs text-slate-500">{Object.values(c.config).join(" · ")}</span></span></li>)}</ul>
                  {EXTRAS && <><label className="mt-3 flex items-center gap-2 text-sm">
                    <input data-testid="answer-calls" type="checkbox" checked={Boolean(st.channels.twilio_voice?.enabled)} onChange={(e) => update({ channels: { ...st.channels, twilio_voice: { enabled: e.target.checked, config: st.channels.twilio_voice?.config ?? {} } } })} />
                    Answer phone calls to your SMS number with the assistant
                  </label>
                  <p className="mt-1 pl-6 text-xs text-slate-500">Emergencies go straight to your on-call number. Needs a Twilio number.</p></>}
                  <label className="mt-3 flex items-center gap-2 text-sm">
                    <input data-testid="twilio-whatsapp" type="checkbox" checked={Boolean(st.channels.twilio_whatsapp?.enabled)} onChange={(e) => update({ channels: { ...st.channels, twilio_whatsapp: { enabled: e.target.checked, config: st.channels.twilio_whatsapp?.config ?? {} } } })} />
                    Answer WhatsApp messages with the assistant (through Twilio)
                  </label>
                  <p className="mt-1 pl-6 text-xs text-slate-500">Needs a Twilio number approved for WhatsApp.</p>
                </Card>
          
        </>
      )}
      <Card id="calendar" title="Calendar" actions={<Button tone="secondary" onClick={connectGoogle}>Connect Google Calendar</Button>}>
        <p className="text-sm">System of record: <strong>{integ?.system_of_record ?? "…"}</strong></p>
        <ul className="mt-2 text-sm">{(integ?.items ?? []).map((i) => <li key={i.id} className="flex justify-between border-t border-slate-100 py-1"><span>{i.provider}</span><span className="flex gap-2"><Badge tone={i.health === "connected" ? "green" : "slate"}>{i.health}</Badge>{i.health === "connected" && <button className="text-xs text-red-600" onClick={() => post(`/integrations/${i.id}/disconnect`).then(load)}>disconnect</button>}</span></li>)}</ul>
      </Card>
      {!SIMPLE_PILOT && (
        <>
          <AlertsCard />
          {EXTRAS && <AgentKeysCard assistant={String(st.assistant ?? "built_in")} onAssistant={(v) => update({ assistant: v })} />}
          {EXTRAS && <BookingBridgeCard onChange={load} />}
        </>
      )}
      {!SIMPLE_PILOT && (
        <>
                <Card id="team" title="Team">
                  {issued && (
                    <div data-testid="staff-code" className="mb-3 rounded-xl bg-brand-50 p-3 text-sm ring-1 ring-inset ring-brand-100">
                      <div>Sign-in code for <strong>{issued.email}</strong>. Send it to them; it is shown once.</div>
                      <div className="my-2 select-all font-mono text-xl font-semibold tracking-[0.2em]">{issued.code}</div>
                      <button className="text-xs font-medium text-brand-700 underline" onClick={() => setIssued(null)}>Done</button>
                    </div>
                  )}
                  <ul className="divide-y divide-slate-100 text-sm">{staff.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center gap-2 py-2">
                      <span className="min-w-0 flex-1 truncate">{u.email}</span>
                      {codes && <button className="text-xs font-medium text-brand-700" onClick={() => newCode(u)}>New code</button>}
                      <select aria-label={`Role for ${u.email}`} value={u.role} onChange={(e) => put(`/settings/staff/${u.id}`, { role: e.target.value }).then(load).catch((er: Error) => setErr(er.message))}>{["owner", "staff", "viewer"].map((r) => <option key={r} value={r}>{ROLE_NAME[r]}</option>)}</select>
                    </li>
                  ))}</ul>
                  <form className="mt-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addStaff(); }}>
                    <input type="email" required aria-label="Email" className="min-w-0 flex-1" placeholder="name@yourbusiness.com" value={newStaff.email} onChange={(e) => setNewStaff({ ...newStaff, email: e.target.value })} />
                    <select aria-label="Role" value={newStaff.role} onChange={(e) => setNewStaff({ ...newStaff, role: e.target.value })}>{["owner", "staff", "viewer"].map((r) => <option key={r} value={r}>{ROLE_NAME[r]}</option>)}</select>
                    <Button type="submit" tone="secondary">Add</Button>
                  </form>
                  <p className="mt-2 text-xs text-slate-500">Team: replies and approvals. View only: reads, private answers hidden.</p>
                </Card>
          
        </>
      )}
      <Card id="widget" title="Website chat">
        <p className="mb-2 text-xs text-slate-500">Paste before the closing body tag of your website.</p>
        <pre data-testid="widget-snippet" className="overflow-x-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">{snippet}</pre>
        <label className="mt-3 flex flex-col gap-1 text-sm">Websites allowed to show your chat
          <input data-testid="widget-origins" className="w-full" placeholder="https://www.yourbusiness.co.uk" value={((st.widget_origins as string[] | undefined) ?? []).join(", ")} onChange={(e) => update({ widget_origins: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
        </label>
        <p className="mt-1 text-xs text-slate-500">
          {((st.widget_origins as string[] | undefined) ?? []).length ? "Only these websites can use your chat." : "Empty: any website could copy your chat. Add yours."}
        </p>
      </Card>
      {!SIMPLE_PILOT && (
              <Card id="data" title="Customer data">
                <label className="flex flex-col gap-1 text-sm">Delete a customer after this many quiet days
                  <input data-testid="retention-days" type="number" min={30} max={3650} className="w-40" value={(st.retention_days as number | undefined) ?? 730} onChange={(e) => update({ retention_days: Number(e.target.value) })} />
                </label>
                <p className="mt-1 text-xs text-slate-500">Their messages, bookings and photos go with them.</p>
                <label className="mt-4 flex flex-col gap-1 text-sm">Privacy notice link <span className="text-xs font-normal text-slate-500">Shown in the first reply to each customer.</span>
                  <input data-testid="privacy-url" className="w-full" placeholder="https://www.yourbusiness.co.uk/privacy" value={(st.privacy_url as string | null | undefined) ?? ""} onChange={(e) => update({ privacy_url: e.target.value || null })} />
                </label>
                <p className="mt-2 text-xs text-slate-500">Export or erase one person from the Customers page.</p>
              </Card>
      )}

    </div>
  );
}
