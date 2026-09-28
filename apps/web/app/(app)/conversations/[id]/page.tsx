"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { post } from "@/lib/api";
import { STATUS_LABEL, when } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Msg = { id: string; direction: string; author: string; body: string; at: string; media?: { url: string | null; content_type: string | null; filename: string | null; error: string | null; transcript?: string | null; transcript_error?: string | null }[] };
type Conv = { id: string; status: string; channel: string; summary: string | null; contact: { display_name: string | null; consent: { status?: string } }; extracted: Record<string, string>; sensitive_keys: string[]; messages: Msg[] };

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, refresh } = usePoll<Conv>(`/conversations/${id}`, 4000);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const act = async (path: string, body?: unknown) => {
    setErr(null);
    try {
      await post(`/conversations/${id}/${path}`, body);
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const suggest = async () => {
    setErr(null);
    try {
      const r = await post<{ suggestion: string }>(`/conversations/${id}/suggest`);
      setDraft(r.suggestion);
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  if (!data) return <ErrorLine error={error} />;
  const human = data.status === "waiting_human";
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 flex flex-col gap-4">
        <Card title={`${data.contact.display_name ?? "Unknown"} · ${data.channel}`} actions={<>
          <Badge tone={human ? "red" : "slate"}>{STATUS_LABEL[data.status] ?? data.status}</Badge>
          {human ? <Button tone="secondary" onClick={() => act("handback")}>Hand back to the worker</Button> : <Button onClick={() => act("takeover")}>Take over</Button>}
          {data.status !== "closed" && <Button tone="secondary" onClick={() => act("close")}>Close</Button>}
        </>}>
          <ErrorLine error={error ?? err} />
          <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
            {data.messages.map((m) => (
              <div key={m.id} className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${m.direction === "inbound" ? "self-start bg-slate-100" : m.author === "human" ? "self-end bg-emerald-100" : "self-end bg-blue-100"}`}>
                <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">{m.author} · {when(m.at)}</div>
                <div className="whitespace-pre-wrap">{m.body}</div>
                {m.media?.map((x, i) => (
                  <div key={i}>
                    {x.url ? <a href={`/api${x.url}`} target="_blank" rel="noreferrer" className="mt-1 block text-xs text-blue-700 underline">{x.content_type?.startsWith("audio/") ? "voice note" : x.filename ?? x.content_type ?? "attachment"}</a> : <span className="mt-1 block text-xs text-red-600">{x.error}</span>}
                    {x.transcript && <p className="mt-1 text-sm italic" data-testid="transcript">&ldquo;{x.transcript}&rdquo; <span className="not-italic text-xs text-slate-500">(transcribed)</span></p>}
                    {!x.transcript && x.transcript_error && <p className="mt-1 text-xs text-slate-500">Voice note not transcribed: {x.transcript_error}</p>}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <textarea data-testid="draft" className="flex-1 rounded border border-slate-300 p-2 text-sm" rows={2} placeholder={human ? "Write to the customer as yourself" : "Take over to write as yourself"} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <div className="flex flex-col gap-2">
              <Button disabled={!draft.trim() || data.contact.consent.status === "opted_out"} onClick={async () => { await act("messages", { body: draft }); setDraft(""); }}>Send</Button>
              <Button tone="secondary" onClick={suggest}>Suggest</Button>
            </div>
          </div>
        </Card>
      </div>
      <div className="flex flex-col gap-4">
        <Card title="Extracted">
          <dl className="text-sm">
            {Object.entries(data.extracted).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2 border-b border-slate-100 py-1">
                <dt className="text-slate-500">{k}{data.sensitive_keys.includes(k) && " 🔒"}</dt>
                <dd className="text-right">{v}</dd>
              </div>
            ))}
            {!Object.keys(data.extracted).length && <p className="text-slate-500">Nothing extracted yet.</p>}
          </dl>
        </Card>
        {data.summary && <Card title="Summary"><p className="whitespace-pre-wrap text-sm">{data.summary}</p></Card>}
        <Card title="Consent"><p className="text-sm">{data.contact.consent.status ?? "unknown"}</p></Card>
      </div>
    </div>
  );
}
