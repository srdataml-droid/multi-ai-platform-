"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { post } from "@/lib/api";
import { STATUS_LABEL, when } from "@/lib/format";
import { label } from "@/lib/proposals";
import { usePoll } from "@/lib/usePoll";

type Msg = { id: string; direction: string; author: string; body: string; at: string; media?: { url: string | null; content_type: string | null; filename: string | null; error: string | null; transcript?: string | null; transcript_error?: string | null }[] };
type Conv = { id: string; status: string; channel: string; summary: string | null; contact: { display_name: string | null; consent: { status?: string } }; extracted: Record<string, string>; sensitive_keys: string[]; messages: Msg[] };

const AUTHOR: Record<string, string> = { worker: "Assistant", human: "Team", customer: "Customer", system: "System" };

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
  const name = data.contact.display_name ?? data.extracted.name ?? "New visitor";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/inbox" aria-label="Back to inbox" className="rounded-lg p-1.5 text-slate-500 ring-1 ring-inset ring-slate-200 hover:bg-white hover:text-slate-900">
          <Icon name="inbox" className="h-4 w-4" />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold tracking-tight">{name}</h1>
          <p className="text-xs text-slate-500">{data.channel}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={human ? "red" : "slate"}>{STATUS_LABEL[data.status] ?? data.status}</Badge>
          {human ? <Button tone="secondary" onClick={() => act("handback")}>Hand back</Button> : <Button onClick={() => act("takeover")}>Take over</Button>}
          {data.status !== "closed" && <Button tone="secondary" onClick={() => act("close")}>Close</Button>}
        </div>
      </div>
      <ErrorLine error={error ?? err} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <div className="flex max-h-[62vh] flex-col gap-3 overflow-y-auto pr-1">
              {data.messages.map((m) => {
                const mine = m.direction !== "inbound";
                return (
                  <div key={m.id} className={`flex max-w-[85%] flex-col ${mine ? "items-end self-end" : "items-start self-start"}`}>
                    <div className={`rounded-2xl px-3.5 py-2 text-sm ${!mine ? "rounded-bl-md bg-slate-100 text-slate-900" : m.author === "human" ? "rounded-br-md bg-emerald-600 text-white" : "rounded-br-md bg-brand-600 text-white"}`}>
                      <div className="whitespace-pre-wrap break-words">{m.body}</div>
                      {m.media?.map((x, i) => (
                        <div key={i}>
                          {x.url ? <a href={`/api${x.url}`} target="_blank" rel="noreferrer" className="mt-1 block text-xs underline opacity-90">{x.content_type?.startsWith("audio/") ? "voice note" : x.filename ?? x.content_type ?? "attachment"}</a> : <span className="mt-1 block text-xs text-red-600">{x.error}</span>}
                          {x.transcript && <p className="mt-1 text-sm italic" data-testid="transcript">&ldquo;{x.transcript}&rdquo; <span className="not-italic text-xs opacity-70">(transcribed)</span></p>}
                          {!x.transcript && x.transcript_error && <p className="mt-1 text-xs opacity-70">Voice note not transcribed: {x.transcript_error}</p>}
                        </div>
                      ))}
                    </div>
                    <div className="mt-1 px-1 text-[11px] text-slate-500">{AUTHOR[m.author] ?? m.author} · {when(m.at)}</div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex items-end gap-2 border-t border-slate-100 pt-4">
              <textarea data-testid="draft" className="min-h-11 flex-1 resize-none" rows={2} placeholder={human ? "Write to the customer" : "Take over to write as yourself"} value={draft} onChange={(e) => setDraft(e.target.value)} />
              <div className="flex flex-col gap-2">
                <Button disabled={!draft.trim() || data.contact.consent.status === "opted_out"} onClick={async () => { await act("messages", { body: draft }); setDraft(""); }}>Send</Button>
                <Button tone="secondary" onClick={suggest}>Suggest</Button>
              </div>
            </div>
          </Card>
        </div>
        <div className="flex flex-col gap-4">
          <Card title="Details">
            <dl className="text-sm">
              {Object.entries(data.extracted).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
                  <dt className="text-slate-500 first-letter:uppercase">{label(k)}{data.sensitive_keys.includes(k) && <span title="Private" aria-label="private"> 🔒</span>}</dt>
                  <dd className="text-right text-slate-900">{v}</dd>
                </div>
              ))}
              {!Object.keys(data.extracted).length && <p className="text-slate-500">Nothing yet.</p>}
            </dl>
            <p className="mt-3 text-xs text-slate-500">Consent: {data.contact.consent.status ?? "unknown"}</p>
          </Card>
          {data.summary && <Card title="Summary"><p className="whitespace-pre-wrap text-sm text-slate-700">{data.summary}</p></Card>}
        </div>
      </div>
    </div>
  );
}
