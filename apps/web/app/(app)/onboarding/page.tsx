"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { api, post } from "@/lib/api";

type Hours = { open: string; close: string };
type Service = { code: string; name: string; duration_minutes: number; auto_confirm: boolean };
type Wizard = {
  business_name: string;
  timezone: string;
  business_hours: Record<string, Hours>;
  services: Service[];
  service_area: string[];
  webchat: boolean;
  sms_number: string | null;
  email_from: string | null;
  on_call: { name: string; phone: string | null; email: string | null };
};
type Onboarding = { pack: { id: string; name: string }; onboarded_at: string | null; wizard: Wizard; google_calendar_available: boolean };

const DAYS: [string, string][] = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
const ZONES = ["Europe/London", "Europe/Dublin", "Africa/Lagos", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"];
const STEPS = ["Business", "Hours", "Services", "Area", "Channels", "Calendar", "On call", "Review"];
const DRAFT = "novaxis:onboarding-draft";
const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm";

function loadDraft(): { step: number; wizard: Wizard } | null {
  try {
    const raw = localStorage.getItem(DRAFT);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveDraft(step: number, wizard: Wizard | null) {
  try {
    if (wizard) localStorage.setItem(DRAFT, JSON.stringify({ step, wizard }));
    else localStorage.removeItem(DRAFT);
  } catch {
    /* storage unavailable: the wizard still works, it just forgets on reload */
  }
}

const codeFrom = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "service";

export default function OnboardingPage() {
  const [data, setData] = useState<Onboarding | null>(null);
  const [w, setW] = useState<Wizard | null>(null);
  const [step, setStep] = useState(0);
  const [calendar, setCalendar] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Onboarding>("/onboarding")
      .then((d) => {
        setData(d);
        const draft = loadDraft();
        setW(draft?.wizard ?? d.wizard);
        setStep(draft?.step ?? 0);
      })
      .catch((e: Error) => setErr(e.message));
    api<{ system_of_record: string | null }>("/integrations").then((d) => setCalendar(d.system_of_record)).catch(() => null);
  }, []);

  useEffect(() => {
    if (w) saveDraft(step, w);
  }, [w, step]);

  if (!data || !w) return <ErrorLine error={err} />;
  const patch = (p: Partial<Wizard>) => setW({ ...w, ...p });

  const finish = async () => {
    setErr(null);
    setBusy(true);
    try {
      await post("/onboarding", { ...w, sms_number: w.sms_number || null, email_from: w.email_from || null, on_call: { ...w.on_call, phone: w.on_call.phone || null, email: w.on_call.email || null } });
      saveDraft(0, null);
      // A full load, so the menu re-reads the tenant and stops sending the owner back here.
      window.location.href = "/inbox";
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
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

  const body = [
    <div key="business" className="flex flex-col gap-3">
      <label className="text-sm">Business name<input className={input} value={w.business_name} onChange={(e) => patch({ business_name: e.target.value })} /></label>
      <label className="text-sm">Time zone
        <select className={input} value={w.timezone} onChange={(e) => patch({ timezone: e.target.value })}>
          {ZONES.map((z) => <option key={z}>{z}</option>)}
        </select>
      </label>
      <p className="text-xs text-slate-500">Business type: <strong>{data.pack.name}</strong></p>
    </div>,
    <div key="hours" className="flex flex-col gap-2">
      {DAYS.map(([k, label]) => {
        const h = w.business_hours[k];
        const toggle = (on: boolean) => {
          const next = { ...w.business_hours };
          if (on) next[k] = { open: "08:00", close: "18:00" };
          else delete next[k];
          patch({ business_hours: next });
        };
        return (
          <div key={k} className="flex items-center gap-3 text-sm">
            <label className="flex w-32 items-center gap-2"><input type="checkbox" checked={!!h} onChange={(e) => toggle(e.target.checked)} />{label}</label>
            {h ? (
              <>
                <input type="time" className="rounded border border-slate-300 px-2 py-1" value={h.open} onChange={(e) => patch({ business_hours: { ...w.business_hours, [k]: { ...h, open: e.target.value } } })} />
                <span>to</span>
                <input type="time" className="rounded border border-slate-300 px-2 py-1" value={h.close} onChange={(e) => patch({ business_hours: { ...w.business_hours, [k]: { ...h, close: e.target.value } } })} />
              </>
            ) : <span className="text-slate-500">Closed</span>}
          </div>
        );
      })}
    </div>,
    <div key="services" className="flex flex-col gap-2">
      <p className="text-xs text-slate-500">What customers can book. These came from the {data.pack.name} template; change anything.</p>
      {w.services.map((s, i) => (
        <div key={i} className="flex items-end gap-2 text-sm">
          <label className="flex-1">Name<input className={input} value={s.name} onChange={(e) => { const next = [...w.services]; next[i] = { ...s, name: e.target.value }; patch({ services: next }); }} /></label>
          <label className="w-28">Minutes<input type="number" min={5} max={480} className={input} value={s.duration_minutes} onChange={(e) => { const next = [...w.services]; next[i] = { ...s, duration_minutes: Number(e.target.value) }; patch({ services: next }); }} /></label>
          <Button tone="secondary" onClick={() => patch({ services: w.services.filter((_, j) => j !== i) })}>Remove</Button>
        </div>
      ))}
      <div><Button tone="secondary" onClick={() => { const name = `New service ${w.services.length + 1}`; patch({ services: [...w.services, { code: codeFrom(name), name, duration_minutes: 60, auto_confirm: false }] }); }}>Add a service</Button></div>
    </div>,
    <div key="area" className="flex flex-col gap-2">
      <label className="text-sm">Postcode areas you cover (comma separated)
        <input className={input} placeholder="SW1, SE1, N" value={w.service_area.join(", ")} onChange={(e) => patch({ service_area: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
      </label>
      <p className="text-xs text-slate-500">Leave empty to accept customers from anywhere (usual for a dental practice). Out-of-area enquiries get a polite no and the team is told.</p>
    </div>,
    <div key="channels" className="flex flex-col gap-3 text-sm">
      <label className="flex items-center gap-2"><input type="checkbox" checked={w.webchat} onChange={(e) => patch({ webchat: e.target.checked })} /> Chat on your website (you get a one-line snippet in Settings)</label>
      <label>Text number customers message (optional)<input className={input} placeholder="+447700900123" value={w.sms_number ?? ""} onChange={(e) => patch({ sms_number: e.target.value })} /></label>
      <label>Email replies come from (optional)<input className={input} placeholder="hello@yourbusiness.co.uk" value={w.email_from ?? ""} onChange={(e) => patch({ email_from: e.target.value })} /></label>
      <p className="text-xs text-slate-500">Text and email need Novaxis to connect the number or domain. Leave them blank now and add them later.</p>
    </div>,
    <div key="calendar" className="flex flex-col gap-3 text-sm">
      <p>Bookings are checked against: <Badge tone={calendar === "google_calendar" ? "green" : "slate"}>{calendar === "google_calendar" ? "Google Calendar" : "your opening hours"}</Badge></p>
      {data.google_calendar_available ? (
        calendar !== "google_calendar" && <div><Button onClick={connectGoogle}>Connect Google Calendar</Button><p className="mt-1 text-xs text-slate-500">Your answers here are kept. After connecting, open Setup from the menu to finish.</p></div>
      ) : (
        <p className="text-xs text-slate-500">Calendar connection is not switched on for this deployment. Offers use your opening hours, and every booking waits for your approval.</p>
      )}
    </div>,
    <div key="oncall" className="flex flex-col gap-3 text-sm">
      <p className="text-xs text-slate-500">Who the worker alerts for emergencies and anything it should not handle alone.</p>
      <label>Name<input className={input} value={w.on_call.name} onChange={(e) => patch({ on_call: { ...w.on_call, name: e.target.value } })} /></label>
      <label>Mobile<input className={input} placeholder="+447700900123" value={w.on_call.phone ?? ""} onChange={(e) => patch({ on_call: { ...w.on_call, phone: e.target.value } })} /></label>
      <label>Email<input className={input} value={w.on_call.email ?? ""} onChange={(e) => patch({ on_call: { ...w.on_call, email: e.target.value } })} /></label>
    </div>,
    <dl key="review" className="grid grid-cols-[10rem_1fr] gap-y-2 text-sm">
      <dt className="text-slate-500">Business</dt><dd>{w.business_name} · {w.timezone}</dd>
      <dt className="text-slate-500">Open</dt><dd>{DAYS.filter(([k]) => w.business_hours[k]).map(([k, l]) => `${l.slice(0, 3)} ${w.business_hours[k].open}–${w.business_hours[k].close}`).join(", ") || "No hours set"}</dd>
      <dt className="text-slate-500">Services</dt><dd>{w.services.map((s) => `${s.name} (${s.duration_minutes} min)`).join(", ")}</dd>
      <dt className="text-slate-500">Area</dt><dd>{w.service_area.join(", ") || "Anywhere"}</dd>
      <dt className="text-slate-500">Channels</dt><dd>{[w.webchat && "Website chat", w.sms_number && `Text ${w.sms_number}`, w.email_from && `Email ${w.email_from}`].filter(Boolean).join(", ") || "None yet"}</dd>
      <dt className="text-slate-500">Calendar</dt><dd>{calendar === "google_calendar" ? "Google Calendar" : "Opening hours"}</dd>
      <dt className="text-slate-500">On call</dt><dd>{w.on_call.name} {w.on_call.phone} {w.on_call.email}</dd>
    </dl>,
  ];

  const last = step === STEPS.length - 1;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <ol className="flex flex-wrap gap-1 text-xs" data-testid="wizard-steps">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button onClick={() => setStep(i)} className={`rounded-full px-3 py-1 ${i === step ? "bg-brand-600 text-white" : i < step ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-500"}`}>{i + 1}. {s}</button>
          </li>
        ))}
      </ol>
      <Card title={data.onboarded_at ? `Setup: ${STEPS[step]}` : `Set up your AI worker: ${STEPS[step]}`}>
        <ErrorLine error={err} />
        {body[step]}
        <div className="mt-6 flex justify-between">
          <Button tone="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</Button>
          {last ? <Button onClick={finish} disabled={busy}>{busy ? "Saving…" : data.onboarded_at ? "Save changes" : "Confirm and go live"}</Button> : <Button onClick={() => setStep(step + 1)}>Next</Button>}
        </div>
      </Card>
    </div>
  );
}
