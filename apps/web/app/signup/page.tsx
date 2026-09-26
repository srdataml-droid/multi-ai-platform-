"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, ErrorLine } from "@/components/ui";
import { getToken, setToken } from "@/lib/auth";

type Options = { mode: "dev" | "demo" | "supabase" | "none"; trial_days: number; trial_reply_cap: number; packs: { id: string; name: string }[] };

export default function SignupPage() {
  const router = useRouter();
  const [opts, setOpts] = useState<Options | null>(null);
  const [form, setForm] = useState({ business_name: "", email: "", pack_id: "hvac", passcode: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      router.replace("/onboarding");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="mx-auto mt-16 max-w-lg px-4">
      <Card title="Start a free trial">
        {opts && (
          <p className="mb-4 text-sm text-slate-600">
            {opts.trial_days} days or {opts.trial_reply_cap} AI replies, whichever comes first. Every feature on. No card needed.
          </p>
        )}
        <ErrorLine error={error} />
        {opts?.mode === "none" ? (
          <p className="text-sm text-red-600">Sign-up is not open on this deployment.</p>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <label className="text-sm">Business name<input data-testid="business-name" required className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={form.business_name} onChange={set("business_name")} /></label>
            <label className="text-sm">Your email<input data-testid="signup-email" type="email" required className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={form.email} onChange={set("email")} /></label>
            <fieldset>
              <legend className="mb-2 text-sm">What kind of business?</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {opts?.packs.map((p) => (
                  <label key={p.id} className={`cursor-pointer rounded border px-3 py-2 text-sm ${form.pack_id === p.id ? "border-slate-900 bg-slate-50" : "border-slate-200"}`}>
                    <input type="radio" name="pack" className="mr-2" checked={form.pack_id === p.id} onChange={() => setForm({ ...form, pack_id: p.id })} />
                    {p.name}
                  </label>
                ))}
              </div>
            </fieldset>
            {opts?.mode === "demo" && (
              <label className="text-sm">Demo passcode<input type="password" data-testid="signup-passcode" className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={form.passcode} onChange={set("passcode")} /></label>
            )}
            <Button type="submit" disabled={busy || !opts}>{busy ? "Creating…" : "Create my account"}</Button>
          </form>
        )}
        <p className="mt-4 text-xs text-slate-500">Already set up? <Link className="underline" href="/login">Sign in</Link></p>
      </Card>
    </div>
  );
}
