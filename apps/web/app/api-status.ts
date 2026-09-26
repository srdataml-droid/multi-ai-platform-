// Server-side fetch of the API's health and version. Kept out of the page so it
// can be unit-tested without rendering React.

export type ApiStatus = {
  reachable: boolean;
  health?: string;
  version?: string;
  commit?: string;
};

const apiBase = process.env.NOVAXIS_API_URL ?? "http://localhost:8000";

export async function getApiStatus(fetchImpl: typeof fetch = fetch): Promise<ApiStatus> {
  try {
    const [h, v] = await Promise.all([
      fetchImpl(`${apiBase}/health`, { cache: "no-store" }),
      fetchImpl(`${apiBase}/version`, { cache: "no-store" }),
    ]);
    if (!h.ok || !v.ok) return { reachable: false };
    const health = (await h.json()) as { status: string };
    const version = (await v.json()) as { version: string; commit: string };
    return { reachable: true, health: health.status, version: version.version, commit: version.commit };
  } catch {
    return { reachable: false };
  }
}
