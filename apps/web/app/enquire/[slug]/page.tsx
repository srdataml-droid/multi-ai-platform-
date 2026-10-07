"use client";

import { use, useEffect, useState } from "react";
import { AuthShell, Field } from "@/components/AuthShell";
import { Button, ErrorLine } from "@/components/ui";

export default function Enquire({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [business, setBusiness] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [requestId, setRequestId] = useState("");
  useEffect(() => {
    setRequestId(crypto.randomUUID());
    fetch(`/api/enquiries/${encodeURIComponent(slug)}`).then(async r => {
      if (!r.ok) throw new Error("This business is not accepting website enquiries here.");
      setBusiness((await r.json()).business_name);
    }).catch(e => setError(e.message));
  }, [slug]);
  return <AuthShell title={done ? "Request received" : business || "Request a callback"}>
    {done ? <p className="text-sm leading-7">Your details have been saved for the team to review. This is not a confirmed callback or engineer booking. No email or text confirmation has been sent.</p> : <>
      <p className="mb-5 text-sm leading-6 text-slate-600">For routine enquiries only. This form is not monitored for emergencies. Your contact details and notes will be saved for this business to respond to your request.</p>
      <ErrorLine error={error} />
      <form className="grid gap-4" onSubmit={async e => {
        e.preventDefault(); if (busy) return; setBusy(true); setError(null);
        const values = Object.fromEntries(new FormData(e.currentTarget));
        try {
          const r = await fetch(`/api/enquiries/${encodeURIComponent(slug)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...values, consent: values.consent === "on", request_id: requestId }) });
          if (!r.ok) throw new Error(r.status === 429 ? "Too many requests. Please try again later." : "Could not save the request. Check your details and retry.");
          setDone(true);
        } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
      }}>
        <Field label="Name"><input name="name" required maxLength={80} /></Field>
        <Field label="Callback number"><input name="phone" type="tel" required minLength={7} maxLength={25} pattern="[+0-9 ()\-]+" /></Field>
        <Field label="Email"><input name="email" type="email" required maxLength={120} /></Field>
        <Field label="Postcode"><input name="postcode" required minLength={2} maxLength={12} /></Field>
        <Field label="Service"><select name="service"><option>Boiler service</option><option>Boiler replacement quote</option><option>Routine plumbing repair</option></select></Field>
        <Field label="Job details"><textarea name="details" required maxLength={1000} rows={3} /></Field>
        <Field label="Preferred callback date, time and time zone"><input name="preferred_window" required maxLength={160} placeholder="e.g. 20 October, 2–4pm UK time" /></Field>
        <label className="flex items-start gap-2 text-sm leading-6"><input name="consent" type="checkbox" required className="mt-1.5" />I agree that this business may use these details to contact me about this enquiry.</label>
        <Button type="submit" disabled={!business || busy || !requestId}>{busy ? "Saving…" : "Request callback"}</Button>
      </form>
    </>}
  </AuthShell>;
}
