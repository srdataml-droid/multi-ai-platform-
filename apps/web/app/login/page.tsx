"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthShell, Field } from "@/components/AuthShell";
import { Icon, type IconName } from "@/components/icons";
import { ErrorLine } from "@/components/ui";
import { type AuthConfig, devLogin, fetchAuthConfig, setToken, supabaseLogin } from "@/lib/auth";

// Who is signing in. The account decides what they can do; this only picks the right
// words, the right code and where to go next.
type Who = "owner" | "team" | "operator";
const WHO: Record<Who, { tab: string; icon: IconName; code: string; demoEmail: string; next: string }> = {
  owner: { tab: "Business owner", icon: "briefcase", code: "Login code", demoEmail: "owner@demo-hvac.test", next: "/inbox" },
  team: { tab: "Team member", icon: "users", code: "Code from your owner", demoEmail: "viewer@demo-hvac.test", next: "/inbox" },
  operator: { tab: "Novaxis", icon: "shield", code: "Operator passcode", demoEmail: "operator@novaxis.test", next: "/operator" },
};
const REMEMBER = "novaxis:who";

export default function LoginPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [who, setWho] = useState<Who>("owner");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchAuthConfig().then(setCfg).catch(() => setCfg({ mode: "dev", supabase_url: "", supabase_anon_key: "" }));
    try {
      const saved = localStorage.getItem(REMEMBER) as Who | null;
      if (saved && saved in WHO) setWho(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);
  // Local mode signs in without a code, so offer a seeded account to try.
  useEffect(() => {
    if (cfg?.mode === "dev") setEmail((e) => (!e || Object.values(WHO).some((w) => w.demoEmail === e) ? WHO[who].demoEmail : e));
  }, [cfg, who]);

  const choose = (w: Who) => {
    setWho(w);
    setError(null);
    try {
      localStorage.setItem(REMEMBER, w);
    } catch {
      /* storage unavailable */
    }
  };
  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const token =
        cfg?.mode === "supabase" ? await supabaseLogin(cfg, email, password) : await devLogin(email, cfg?.mode === "demo" ? passcode : undefined);
      setToken(token);
      router.replace(WHO[who].next);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const footer =
    who === "owner" ? (
      <>New business? <Link className="font-medium text-brand-700 hover:underline" href="/signup">Start a free trial</Link></>
    ) : who === "team" ? (
      <>No code? Ask the owner to add you in Settings.</>
    ) : null;

  return (
    <AuthShell title="Sign in" footer={cfg && cfg.mode !== "none" ? footer : null}>
      <div role="radiogroup" aria-label="I am" className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        {(["owner", "team"] as const).map((w) => (
          <button key={w} type="button" role="radio" aria-checked={who === w} onClick={() => choose(w)} className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-sm font-medium transition ${who === w ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}>
            <Icon name={WHO[w].icon} className="h-4 w-4" />
            {WHO[w].tab}
          </button>
        ))}
      </div>
      {who === "operator" && <p className="-mt-2 mb-4 flex items-center gap-1.5 text-xs font-medium text-brand-700"><Icon name="shield" className="h-4 w-4" />Novaxis operator</p>}
      <ErrorLine error={error} />
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Email">
          <input data-testid="email" type="email" autoComplete="username" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        {cfg?.mode === "supabase" && (
          <Field label="Password">
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        )}
        {cfg?.mode === "demo" && (
          <Field label={WHO[who].code}>
            <input type="password" data-testid="passcode" autoComplete="current-password" value={passcode} onChange={(e) => setPasscode(e.target.value)} />
          </Field>
        )}
        {cfg?.mode === "none" && <p className="text-sm text-red-600">Sign-in is not set up here.</p>}
        <button type="submit" disabled={busy || cfg?.mode === "none"} className="mt-1 min-h-11 rounded-xl bg-brand-600 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <div className="mt-4 text-center">
        <button type="button" className="text-xs text-slate-500 hover:text-slate-800" onClick={() => choose(who === "operator" ? "owner" : "operator")}>
          {who === "operator" ? "Back to business sign-in" : "Novaxis staff"}
        </button>
      </div>
    </AuthShell>
  );
}
