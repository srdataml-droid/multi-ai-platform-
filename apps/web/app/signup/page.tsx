"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthShell, Field } from "@/components/AuthShell";
import { ErrorLine } from "@/components/ui";
import { getToken, setToken } from "@/lib/auth";

type Options = { mode: "dev" | "demo" | "supabase" | "none"; trial_days: number; trial_reply_cap: number; packs: { id: string; name: string }[] };

const primary = "min-h-11 w-full rounded-xl bg-brand-600 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60";

export default function SignupPage() {
  const router = useRouter();
  const [opts, setOpts] = useState<Options | null>(null);
  const [form, setForm] = useState({ business_name: "", email: "", pack_id: "hvac", passcode: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/signup/options").then((r) => r.json()).then(setOpts).catch(() => setError("The API is not reachable."));
  }, []);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      // Supabase mode: the account was created on the sign-in page and its token is held already.
      if (opts?.mode === "supabase" && getToken()) headers.Authorization = `Bearer ${getToken()}`;
      const body = { business_name: form.business_name, email: form.email, pack_id: form.pack_id, ...(opts?.mode === "demo" ? { passcode: form.passcode } : {}) };
      const r = await fetch("/api/signup", { method: "POST", headers, body: JSON.stringify(body) });
      const data = await r.json();
      if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "sign-up failed");
      if (data.token) setToken(data.token);
      if (data.login_code) setCode(data.login_code);
      else router.replace("/onboarding");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  if (code) {
    return (
      <AuthShell title="Save your login code">
        <p className="text-sm text-slate-600">You sign in with your email and this code. It is shown once.</p>
        <p data-testid="login-code" className="my-5 select-all rounded-2xl bg-slate-100 px-4 py-4 text-center font-mono text-2xl font-semibold tracking-[0.2em]">{code}</p>
        <button className={primary} onClick={() => router.replace("/onboarding")}>I have saved it, continue</button>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Start your free trial"
      footer={<>Already have an account? <Link className="font-medium text-brand-700 hover:underline" href="/login">Sign in</Link></>}
    >
      {opts && <p className="-mt-2 mb-4 text-sm text-slate-500">{opts.trial_days} days or {opts.trial_reply_cap} AI replies. No card.</p>}
      <ErrorLine error={error} />
      {opts?.mode === "none" ? (
        <p className="text-sm text-red-600">Sign-up is not open here.</p>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <Field label="Business name">
            <input data-testid="business-name" required autoComplete="organization" value={form.business_name} onChange={set("business_name")} />
          </Field>
          <Field label="Your email">
            <input data-testid="signup-email" type="email" required autoComplete="email" inputMode="email" value={form.email} onChange={set("email")} />
          </Field>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium text-slate-700">Your kind of business</legend>
            <div className="flex flex-col gap-2">
              {opts?.packs.map((p) => (
                <label key={p.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 text-sm transition ${form.pack_id === p.id ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-500" : "border-slate-200 hover:border-slate-300"}`}>
                  <input type="radio" name="pack" checked={form.pack_id === p.id} onChange={() => setForm({ ...form, pack_id: p.id })} />
                  {p.name}
                </label>
              ))}
            </div>
          </fieldset>
          {opts?.mode === "demo" && (
            <Field label="Demo passcode">
              <input type="password" data-testid="signup-passcode" value={form.passcode} onChange={set("passcode")} />
            </Field>
          )}
          <button type="submit" className={primary} disabled={busy || !opts}>{busy ? "Creating…" : "Create my account"}</button>
        </form>
      )}
    </AuthShell>
  );
}
