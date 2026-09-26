// Token storage and login. Local dev mints a token from the API; production signs in
// with Supabase Auth's password grant and uses that JWT the same way. No SDK needed.
"use client";

const KEY = "novaxis:token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}

// While an operator is inside a customer's tenant, their own token waits here so
// "Exit" can return them to the console without signing in again.
const OPERATOR_KEY = "novaxis:operator-token";

export function enterTenant(tenantToken: string): void {
  const own = getToken();
  try {
    if (own) localStorage.setItem(OPERATOR_KEY, own);
  } catch {
    /* storage unavailable */
  }
  setToken(tenantToken);
}

export function exitTenant(): boolean {
  let own: string | null = null;
  try {
    own = localStorage.getItem(OPERATOR_KEY);
    localStorage.removeItem(OPERATOR_KEY);
  } catch {
    /* storage unavailable */
  }
  setToken(own);
  return own !== null;
}

export type AuthConfig = { mode: "dev" | "demo" | "supabase" | "none"; supabase_url: string; supabase_anon_key: string };

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const r = await fetch("/api/auth/config");
  return (await r.json()) as AuthConfig;
}

export async function devLogin(email: string, passcode?: string): Promise<string> {
  const r = await fetch("/api/auth/dev-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(passcode ? { email, passcode } : { email }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? "login failed");
  return ((await r.json()) as { token: string }).token;
}

export async function supabaseLogin(cfg: AuthConfig, email: string, password: string): Promise<string> {
  const r = await fetch(`${cfg.supabase_url}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: cfg.supabase_anon_key },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error("sign-in failed");
  return ((await r.json()) as { access_token: string }).access_token;
}
