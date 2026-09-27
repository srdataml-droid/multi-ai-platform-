"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, ErrorLine } from "@/components/ui";
import { type AuthConfig, devLogin, fetchAuthConfig, setToken, supabaseLogin } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("owner@demo-hvac.test");
  const [password, setPassword] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetchAuthConfig().then(setCfg).catch(() => setCfg({ mode: "dev", supabase_url: "", supabase_anon_key: "" }));
  }, []);
  const submit = async () => {
    setError(null);
    try {
      const token =
        cfg?.mode === "supabase" ? await supabaseLogin(cfg, email, password) : await devLogin(email, cfg?.mode === "demo" ? passcode : undefined);
      setToken(token);
      router.replace("/inbox");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="mx-auto mt-24 max-w-sm">
      <Card title="Sign in">
        <ErrorLine error={error} />
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <label className="text-sm">Email<input data-testid="email" className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          {cfg?.mode === "supabase" && (
            <label className="text-sm">Password<input type="password" className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          )}
          {cfg?.mode === "demo" && (
            <label className="text-sm">Passcode or your login code<input type="password" data-testid="passcode" className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5" value={passcode} onChange={(e) => setPasscode(e.target.value)} /></label>
          )}
          {cfg?.mode === "dev" && <p className="text-xs text-slate-500">Local mode: any seeded email signs in without a password.</p>}
          {cfg?.mode === "none" && <p className="text-xs text-red-600">Sign-in is not configured on this deployment.</p>}
          <Button type="submit">Sign in</Button>
        </form>
        {cfg && cfg.mode !== "none" && <p className="mt-4 text-xs text-slate-500">New business? <Link className="underline" href="/signup">Start a free trial</Link></p>}
      </Card>
    </div>
  );
}
