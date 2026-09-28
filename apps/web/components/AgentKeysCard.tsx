"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { api, post } from "@/lib/api";
import { ago } from "@/lib/format";

type Key = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null };

// Settings card: who answers customers, and keys for the business's own agent (docs/agent-api.md).
export function AgentKeysCard({ assistant, onAssistant }: { assistant: string; onAssistant: (v: "built_in" | "external") => void }) {
  const [keys, setKeys] = useState<Key[]>([]);
  const [name, setName] = useState("hermes");
  const [shown, setShown] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api<{ items: Key[] }>("/settings/agent-keys").then((d) => setKeys(d.items)).catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setErr(null);
    try {
      const r = await post<Key & { key: string }>("/settings/agent-keys", { name });
      setShown(r.key);
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const revoke = async (id: string) => {
    try {
      await api(`/settings/agent-keys/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <Card title="Your own agent (agent API)">
      <ErrorLine error={err} />
      <label className="block text-sm">Who answers customers
        <select data-testid="assistant-mode" className="ml-2 rounded border px-1" value={assistant} onChange={(e) => onAssistant(e.target.value as "built_in" | "external")}>
          <option value="built_in">The built-in assistant</option>
          <option value="external">Our own agent, through the agent API</option>
        </select>
      </label>
      <p className="mt-1 text-xs text-slate-500">
        With your own agent, the built-in assistant stops replying; the emergency check, the AI disclosure and your approval rules still apply to everything your agent proposes. Press Save all at the top.
      </p>
      {shown && (
        <div className="mt-3 rounded bg-amber-50 p-2 text-sm" data-testid="new-agent-key">
          Copy this key now; it will not be shown again:
          <code className="mt-1 block break-all rounded bg-white px-2 py-1 text-xs">{shown}</code>
          <button className="mt-1 text-xs underline" onClick={() => setShown(null)}>I have copied it</button>
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 text-sm">
        <input className="rounded border border-slate-300 px-2 py-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="key name" />
        <Button tone="secondary" onClick={create} disabled={!name.trim()}>Create key</Button>
      </div>
      <ul className="mt-2 text-sm">
        {keys.map((k) => (
          <li key={k.id} className="flex justify-between border-t border-slate-100 py-1">
            <span>{k.name} <code className="text-xs text-slate-500">{k.prefix}…</code></span>
            <span className="flex items-center gap-2 text-xs text-slate-500">
              {k.revoked_at ? <Badge>revoked</Badge> : <>{k.last_used_at ? `used ${ago(k.last_used_at)}` : "never used"}<button className="text-red-600" onClick={() => revoke(k.id)}>revoke</button></>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
