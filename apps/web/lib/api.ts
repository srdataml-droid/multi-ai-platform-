"use client";

import { getToken, setToken } from "./auth";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  // A photo upload (FormData) sets its own multipart boundary; everything else is JSON.
  if (init.body && !(init.body instanceof FormData) && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const r = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  if (r.status === 401) {
    setToken(null);
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "signed out");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = ((await r.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new ApiError(r.status, detail);
  }
  maybeRefresh();
  return (await r.json()) as T;
}

// A signed-in person is not cut off mid-shift: when less than two hours remain, swap the
// token for a fresh one. Operator entries into a tenant are never extended (the API says no).
let refreshing = false;
function maybeRefresh(): void {
  const token = getToken();
  if (!token || refreshing) return;
  let exp = 0;
  try {
    exp = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp ?? 0;
  } catch {
    return;
  }
  if (exp * 1000 - Date.now() > 2 * 3600 * 1000) return;
  refreshing = true;
  fetch("/api/auth/refresh", { method: "POST", headers: { Authorization: `Bearer ${token}` } })
    .then((r) => (r.ok ? r.json() : null))
    .then((d: { token?: string } | null) => { if (d?.token) setToken(d.token); })
    .catch(() => null)
    .finally(() => { refreshing = false; });
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
