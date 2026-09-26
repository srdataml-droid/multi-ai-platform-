import { getApiStatus } from "./api-status";

export const dynamic = "force-dynamic";

export default async function Home() {
  const status = await getApiStatus();
  return (
    <main>
      <h1>Novaxis Worker</h1>
      <p>Dashboard placeholder. Chunk 9 replaces this page.</p>
      <h2>API</h2>
      <ul>
        <li>Reachable: {status.reachable ? "yes" : "no"}</li>
        <li>Health: {status.health ?? "unknown"}</li>
        <li>Version: {status.version ?? "unknown"}</li>
        <li>Commit: {status.commit ?? "unknown"}</li>
      </ul>
    </main>
  );
}
