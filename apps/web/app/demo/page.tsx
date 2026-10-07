"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import { Logo } from "@/components/icons";

type Decision = "pending" | "approved" | "declined";
type Request = { name: string; email: string; phone: string; postcode: string; service: string; details: string; window: string; decision: Decision };
const example: Request = { name: "Jamie Taylor", email: "jamie@example.test", phone: "07700 900123", postcode: "N13 4SD", service: "Boiler service", details: "Annual service for a combi boiler. Access is easiest in the afternoon.", window: "Tomorrow, 14:00–16:00", decision: "pending" };
const windows = ["Tomorrow, 09:00–11:00", "Tomorrow, 14:00–16:00", "Next working day, 16:00–18:00"];
const steps = ["Customer enquiry", "Owner review", "Callback plan"];

export default function DemoPage() {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Request>({ ...example });
  const [request, setRequest] = useState<Request | null>(null);
  const [notice, setNotice] = useState("");
  const reset = () => { setDraft({ ...example }); setRequest(null); setStep(0); setNotice("Demo reset. Start with the fictional enquiry below."); };
  const decide = (decision: Decision) => {
    if (!request || request.decision !== "pending") return;
    setRequest({ ...request, decision });
    setNotice(decision === "approved" ? "Callback approved in this demo. No message was sent." : "Enquiry declined in this demo. No message was sent.");
    setStep(2);
  };

  return (
    <main className="min-h-screen bg-[#f3f4f8]">
      <div className="border-b border-slate-200 bg-white">
        <header className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-5 lg:px-10">
          <Link href="/demo" className="flex items-center gap-2.5 text-xl font-semibold tracking-tight"><Logo className="h-8 w-8" />Novaxis <span className="ml-2 rounded-md bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-[.15em] text-slate-500">Field demo</span></Link>
          <div className="flex items-center gap-4"><Link href="/login" className="text-sm text-slate-500 hover:text-brand-700">Business sign-in</Link><Button tone="secondary" onClick={reset}>Reset demo</Button></div>
        </header>
      </div>
      <div className="mx-auto max-w-7xl px-5 py-10 lg:px-10">
        <div className="mb-9 grid gap-6 lg:grid-cols-[1fr_310px]">
          <div><p className="mb-3 text-xs font-bold uppercase tracking-[.2em] text-brand-600">For independent heating & plumbing teams</p><h1 className="max-w-2xl text-4xl font-semibold leading-[1.15] tracking-tight sm:text-5xl">A useful enquiry.<br /><span className="text-slate-400">Ready when you are.</span></h1><p className="mt-5 max-w-xl text-base leading-7 text-slate-600">Collect the job details while you work. Review the request, choose a callback window, and keep the final decision with your team.</p></div>
          <aside className="self-end rounded-2xl border border-brand-200 bg-brand-50 p-5"><Badge tone="blue">No account needed</Badge><h2 className="mt-3 font-semibold">Try the whole loop in a minute</h2><p className="mt-2 text-sm leading-6 text-slate-600">Fictional data, held only on this page. No calls, emails or bookings are sent. Refreshing clears your progress.</p></aside>
        </div>
        <nav aria-label="Demo steps" className="mb-7 grid grid-cols-3 gap-2">
          {steps.map((label, index) => <button key={label} onClick={() => setStep(index)} aria-current={step === index ? "step" : undefined} className={`flex min-h-16 items-center gap-3 rounded-xl border px-3 py-3 text-left text-sm font-medium sm:px-5 ${step === index ? "border-brand-600 bg-brand-600 text-white shadow-lg shadow-brand-200/50" : "border-slate-200 bg-white text-slate-500 hover:border-brand-300"}`}><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs ${step === index ? "bg-white/20" : "bg-slate-100"}`}>{index + 1}</span><span>{label}</span></button>)}
        </nav>
        <p role="status" className="mb-3 min-h-5 text-sm text-brand-700">{notice}</p>
        <div className="grid items-start gap-6 lg:grid-cols-[1fr_310px]">
          <div>
            {step === 0 && <Card title="Northside Heating · fictional business" actions={<Badge>Customer view</Badge>}>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">Tell us what you need</h2><p className="mb-6 mt-2 text-sm text-slate-500">This demo covers routine enquiries only. Do not use it for emergencies or enter real personal details.</p>
              <form onSubmit={e => { e.preventDefault(); if (!draft.name.trim() || !draft.postcode.trim() || !draft.details.trim()) return; setRequest({ ...draft, decision: "pending" }); setNotice("Fictional enquiry captured. Now review it as the owner."); setStep(1); }} className="grid gap-5 sm:grid-cols-2">
                <label className="grid gap-2 text-sm font-medium">Name<input required maxLength={80} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
                <label className="grid gap-2 text-sm font-medium">Email<input required type="email" maxLength={120} value={draft.email} onChange={e => setDraft({ ...draft, email: e.target.value })} /></label>
                <label className="grid gap-2 text-sm font-medium sm:col-span-2">Callback number<input required type="tel" maxLength={25} value={draft.phone} onChange={e => setDraft({ ...draft, phone: e.target.value })} /></label>
                <label className="grid gap-2 text-sm font-medium">Postcode<input required maxLength={12} value={draft.postcode} onChange={e => setDraft({ ...draft, postcode: e.target.value })} /></label>
                <label className="grid gap-2 text-sm font-medium">Service<select value={draft.service} onChange={e => setDraft({ ...draft, service: e.target.value })}><option>Boiler service</option><option>Boiler replacement quote</option><option>Routine plumbing repair</option></select></label>
                <label className="grid gap-2 text-sm font-medium sm:col-span-2">What should we know?<textarea required maxLength={1000} rows={3} value={draft.details} onChange={e => setDraft({ ...draft, details: e.target.value })} /></label>
                <label className="grid gap-2 text-sm font-medium sm:col-span-2">Preferred callback window<select value={draft.window} onChange={e => setDraft({ ...draft, window: e.target.value })}>{windows.map(w => <option key={w}>{w}</option>)}</select></label>
                <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5 sm:col-span-2"><Button type="submit">Send demo enquiry →</Button><span className="text-xs text-slate-500">A callback request, not a confirmed engineer visit.</span></div>
              </form>
            </Card>}
            {step === 1 && <Card title="Needs your decision" actions={<Badge tone="amber">Owner view</Badge>}>
              {!request ? <div className="py-12 text-center"><p className="mb-4 text-slate-500">Send a demo enquiry to see the review card.</p><Button onClick={() => setStep(0)}>Create an enquiry</Button></div> : <>
                <div className="mb-6 flex items-center gap-4 pt-3"><span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-xl font-semibold text-brand-600">{request.name.charAt(0)}</span><div><h2 className="text-2xl font-semibold">{request.name}</h2><p className="mt-1 text-sm text-slate-500">{request.service} · {request.postcode}</p></div></div>
                <div className="mb-6 rounded-xl bg-slate-50 p-5"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Customer notes</p><p className="whitespace-pre-wrap leading-7">{request.details}</p></div>
                <dl className="mb-6 grid gap-5 sm:grid-cols-2"><div><dt className="text-xs text-slate-500">Reply address</dt><dd className="mt-1 break-all text-sm font-medium">{request.email}</dd></div><div><dt className="text-xs text-slate-500">Callback number</dt><dd className="mt-1 text-sm font-medium">{request.phone}</dd></div><div><dt className="text-xs text-slate-500">Decision</dt><dd className="mt-1 text-sm font-medium capitalize">{request.decision}</dd></div></dl>
                <label className="mb-5 grid gap-2 text-sm font-medium">Callback window · change before approving<select disabled={request.decision !== "pending"} value={request.window} onChange={e => setRequest({ ...request, window: e.target.value })}>{windows.map(w => <option key={w}>{w}</option>)}</select></label>
                <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-5"><Button disabled={request.decision !== "pending"} onClick={() => decide("approved")}>Approve callback</Button><Button tone="danger" disabled={request.decision !== "pending"} onClick={() => decide("declined")}>Decline enquiry</Button></div>
              </>}
            </Card>}
            {step === 2 && <Card title="Callback plan" actions={<Badge>Simulated schedule</Badge>}>
              {request?.decision === "approved" ? <div className="py-4"><Badge tone="green">Approved by owner</Badge><h2 className="mt-5 text-2xl font-semibold">{request.window}</h2><p className="mt-2 text-lg text-slate-600">Call {request.name} about {request.service.toLowerCase()}.</p><div className="my-6 border-l-4 border-brand-500 bg-brand-50 p-5"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-600">Customer reply preview · not sent</p><p className="leading-7">Hi {request.name}, we have pencilled in a callback for {request.window.toLowerCase()}. We will discuss the job before agreeing an engineer visit or a price.</p></div><p className="text-sm text-slate-500">No calendar was connected. This is a local demonstration of the approval workflow.</p></div> : <div className="py-12 text-center"><h2 className="text-xl font-semibold">{request?.decision === "declined" ? "Enquiry declined" : "No callback approved yet"}</h2><p className="mx-auto mb-5 mt-3 max-w-sm text-sm leading-6 text-slate-500">{request?.decision === "declined" ? "Nothing was added to the callback plan and no reply was sent. Reset to try a different decision." : "The customer’s preference becomes a callback plan only after the owner approves it."}</p><Button onClick={request?.decision === "declined" ? reset : () => setStep(1)}>{request?.decision === "declined" ? "Try another enquiry" : "Review enquiry"}</Button></div>}
            </Card>}
          </div>
          <aside className="space-y-5"><Card title="One request. A clear next step."><ol className="space-y-5">{["Capture contact, location and job details.", "Let the owner decide what happens next.", "Prepare a callback and a clear reply."].map((text, i) => <li key={text} className="flex gap-3 text-sm leading-6"><span className="font-semibold text-brand-600">0{i + 1}</span><span className="text-slate-600">{text}</span></li>)}</ol></Card><div className="rounded-2xl bg-slate-900 p-6 text-white"><p className="text-xs font-semibold uppercase tracking-wider text-slate-400">The setup service</p><h2 className="mt-3 text-xl font-semibold">Built around your business.</h2><p className="mt-3 text-sm leading-6 text-slate-300">Your services, your area, your enquiry form. Installation, testing and a handover for the person who handles your customers.</p><div className="mt-5 border-t border-slate-700 pt-4 text-xs leading-6 text-slate-400">Demo scope: website enquiries.<br />Piper voice and telephone integrations are not connected.</div></div></aside>
        </div>
        <footer className="mt-10 border-t border-slate-200 pt-5 text-xs leading-6 text-slate-500">Novaxis prototype · Fictional business and customer · No AI model, account access or external services used in this demo.</footer>
      </div>
    </main>
  );
}
