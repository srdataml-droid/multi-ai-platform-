"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, put } from "@/lib/api";
import { Badge, Button, Card, ErrorLine } from "@/components/ui";
import { WebsiteChatSetup } from "@/components/WebsiteChatSetup";

type Configuration = {
  provider: string; scripted: boolean;
  models: { responses: string; classification: string; summaries: string };
  latest_worker_call: { model: string; at: string } | null;
};
type Business = {
  tenant: { slug: string; name: string; pack_id: string; worker_enabled: boolean };
  settings: Record<string, unknown> & {
    tone?: string; services?: { code: string; name: string; duration_minutes: number }[];
    widget_origins?: string[];
    faqs?: { question: string; answer: string }[]; service_area?: string[];
    business_hours?: Record<string, { open: string; close: string }>;
    channels?: Record<string, { enabled: boolean }>;
    booking_types?: { id: string; name: string }[];
  };
};
type Message = { id: string; direction: string; author: string; body: string };
type Conversation = { messages: Message[]; status?: string; conversation_id?: string };

// Visitor requests deliberately omit staff credentials and do not sign an owner out
// when a visitor token expires. They use the same channel as the installed widget.
async function visitorRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = "The chat service could not complete this request.";
    try { detail = (await response.json()).detail || detail; } catch { /* use fallback */ }
    throw new Error(detail);
  }
  return response.json();
}

function AssistantChat({ business, onReply }: { business: Business; onReply: () => void }) {
  const [token, setToken] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation>({ messages: [] });
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const generation = useRef(0);
  const end = useRef<HTMLDivElement>(null);
  const slug = business.tenant.slug;
  const enabled = business.settings.channels?.webchat?.enabled && business.tenant.worker_enabled;
  const waiting = !!conversation.messages.length && conversation.messages.at(-1)?.direction === "inbound";
  const refreshReply = useRef(onReply);
  refreshReply.current = onReply;

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [conversation.messages, pending]);
  useEffect(() => {
    if (!waiting) { setSlow(false); return; }
    const timer = setTimeout(() => setSlow(true), 30000);
    return () => clearTimeout(timer);
  }, [waiting]);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let busy = false;
    let count = 0;
    const load = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await visitorRequest<Conversation>(`/inbound/webchat/${encodeURIComponent(slug)}/messages?visitor_token=${encodeURIComponent(token)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setConversation(result);
        setError(null);
        const replies = result.messages.filter((m) => m.direction === "outbound").length;
        if (replies !== count) { count = replies; refreshReply.current(); }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally { busy = false; }
    };
    void load();
    const timer = setInterval(() => { if (!document.hidden) void load(); }, 5000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [slug, token]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || pending || !enabled) return;
    const current = generation.current;
    setPending(body); setDraft(""); setError(null);
    try {
      const result = await visitorRequest<{ visitor_token: string; message_id: string; conversation_id: string }>(`/inbound/webchat/${encodeURIComponent(slug)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body, visitor_token: token, page: "/assistant" }),
      });
      if (generation.current !== current) return;
      setToken(result.visitor_token);
      setConversation((previous) => ({ ...previous, conversation_id: result.conversation_id, messages: previous.messages.some((m) => m.id === result.message_id) ? previous.messages : [...previous.messages, { id: result.message_id, direction: "inbound", author: "customer", body }] }));
    } catch (e) {
      if (generation.current === current) { setError((e as Error).message); setDraft(body); }
    } finally { if (generation.current === current) setPending(null); }
  };
  const reset = () => {
    generation.current += 1;
    setToken(null); setConversation({ messages: [] }); setDraft(""); setError(null); setSlow(false);
  };

  return <section className="flex min-h-[36rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <header className="flex items-center justify-between gap-3 border-b border-slate-100 p-5">
      <div><h2 className="font-semibold">Chat with {business.tenant.name}</h2><p className="mt-1 text-xs text-slate-500">Same message flow as your website widget</p></div>
      <Button tone="secondary" onClick={reset} disabled={!!pending}>New conversation</Button>
    </header>
    <p className="border-b border-amber-100 bg-amber-50 px-5 py-3 text-xs leading-relaxed text-amber-900">Messages are saved to this business’s inbox and can create approvals or booking proposals. Use fictional customer details. Starting a new conversation keeps the previous one in the inbox.</p>
    {!enabled && <p className="m-4 rounded-lg bg-slate-100 p-3 text-sm">Enable the assistant and Website chat in <Link className="underline" href="/settings#channels">Settings</Link> to send messages here.</p>}
    <div role="log" aria-label="Chat messages" aria-live="polite" className="flex max-h-[32rem] flex-1 flex-col gap-3 overflow-y-auto p-5">
      {!conversation.messages.length && !pending && <div className="my-auto py-10 text-center"><div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-xl text-brand-700">✦</div><h3 className="font-medium">Try your business assistant</h3><p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-slate-500">Ask about a service, opening hours, or making a booking. Replies use your saved business settings.</p><div className="mt-5 flex flex-wrap justify-center gap-2">{["What services do you offer?", "When are you open?", "I'd like to book a visit."].map((text) => <button key={text} disabled={!enabled} onClick={() => setDraft(text)} className="rounded-full border border-slate-200 px-3 py-2 text-xs hover:bg-slate-50 disabled:opacity-50">{text}</button>)}</div></div>}
      {conversation.messages.map((message) => <div key={message.id} className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${message.direction === "inbound" ? "ml-auto bg-brand-600 text-white" : "mr-auto bg-slate-100 text-slate-800"}`}><p className="mb-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">{message.direction === "inbound" ? "You · visitor" : message.author === "human" ? "Business team" : "Assistant"}</p><p className="whitespace-pre-wrap">{message.body}</p></div>)}
      {pending && <p className="ml-auto max-w-[88%] rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-700">{pending}<span className="mt-1 block text-xs">Sending…</span></p>}
      {waiting && <p role="status" className="text-xs text-slate-500">{conversation.status === "waiting_human" ? "This conversation is waiting for the business team. Check Inbox and Approvals." : slow ? "Still waiting for a reply. Check Inbox, Approvals, and the worker service if it stays here." : "Message received. Waiting for the assistant or business team…"}</p>}
      <div ref={end} />
    </div>
    <div className="px-5"><ErrorLine error={error} />{conversation.conversation_id && <Link href={`/conversations/${conversation.conversation_id}`} className="mb-3 inline-block text-xs font-medium text-brand-700 underline">View conversation in Inbox</Link>}</div>
    <form onSubmit={send} className="flex items-end gap-2 border-t border-slate-100 p-4"><label className="flex-1"><span className="sr-only">Your message</span><textarea rows={2} maxLength={4000} placeholder="Write a test message…" value={draft} onChange={(event) => setDraft(event.target.value)} disabled={!enabled} className="w-full resize-none rounded-xl border border-slate-200 p-3 text-sm" /></label><Button type="submit" disabled={!enabled || !!pending || !draft.trim()}>Send</Button></form>
  </section>;
}

export default function AssistantStudioPage() {
  const [business, setBusiness] = useState<Business | null>(null);
  const [config, setConfig] = useState<Configuration | null>(null);
  const [packName, setPackName] = useState("");
  const [tone, setTone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [snippet, setSnippet] = useState("");
  const refreshModel = () => api<Configuration>("/settings/assistant").then((result) => { setConfig(result); setModelError(null); }).catch((e: Error) => setModelError(e.message));
  useEffect(() => {
    api<Business>("/settings").then((result) => { setBusiness(result); setTone(result.settings.tone || "friendly, brief, plain English"); }).catch((e: Error) => setError(e.message));
    api<{ name: string }>("/pack").then((pack) => setPackName(pack.name)).catch(() => null);
    api<{ snippet: string }>("/settings/widget").then((result) => setSnippet(result.snippet)).catch(() => null);
    void refreshModel();
  }, []);
  const saveTone = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      // Read fresh settings before saving a single field; preserve changes from other pages.
      const current = await api<Business>("/settings");
      const result = await put<Business>("/settings", { settings: { ...current.settings, tone: tone.trim() } });
      setBusiness(result); setSaved(true);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  };
  return <div className="space-y-5">
    <header className="flex flex-wrap items-start justify-between gap-3"><div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-brand-700">Your business, your assistant</p><h1 className="text-2xl font-semibold tracking-tight">Assistant Studio</h1><p className="mt-2 max-w-xl text-sm text-slate-500">Explore replies, see the model behind them, and shape how your business speaks.</p></div><a href="#website-install" className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium">Install on your website →</a></header>
    <ErrorLine error={error} />
    {!business ? <p role="status" className="text-sm text-slate-500">{error ? "Business settings could not be loaded." : "Loading your business…"}</p> : <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,1fr)]">
      <AssistantChat key={business.tenant.slug} business={business} onReply={() => { void refreshModel(); }} />
      <div className="space-y-4">
        <Card title="What powers the replies" actions={<Button tone="secondary" onClick={() => { void refreshModel(); }}>Refresh</Button>}>
          <ErrorLine error={modelError} />
          {!config ? <p className="text-sm text-slate-500">{modelError ? "Model status unavailable. Deploy the API update to enable this panel." : "Loading model details…"}</p> : <>
            <Badge tone={config.scripted ? "amber" : "blue"}>{config.scripted ? "Scripted demo provider" : config.provider}</Badge>
            <dl className="mt-4 space-y-3 text-sm">{Object.entries(config.models).map(([task, model]) => <div key={task} className="flex justify-between gap-3"><dt className="capitalize text-slate-500">{task}</dt><dd className="break-all text-right font-medium">{model}</dd></div>)}</dl>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">Configured on the API server. A separately deployed worker may have different settings.</p>
            <div className="mt-4 rounded-xl bg-slate-50 p-3"><p className="text-xs font-medium text-slate-500">Latest recorded response-model call for this business</p><p className="mt-1 break-all text-sm font-semibold">{config.latest_worker_call?.model || "No worker call recorded yet"}</p>{config.latest_worker_call && <p className="mt-1 text-xs text-slate-500">{new Date(config.latest_worker_call.at).toLocaleString()}</p>}<p className="mt-2 text-xs text-slate-500">A model call is not proof that its reply was delivered.</p></div>
            {config.scripted && <p className="mt-3 text-xs leading-relaxed text-amber-800">Scripted replies check the message flow. They do not demonstrate AI understanding of these business facts.</p>}
            <details className="mt-4 text-xs text-slate-600"><summary className="cursor-pointer font-medium">How to change the model later</summary><p className="mt-2 leading-relaxed">Your administrator sets the provider and response, classification, and summary models on the API and worker deployments. Keep provider keys on the server. After switching, check real replies, booking proposals, and handoffs before inviting customers.</p><p className="mt-2">Supported providers: Anthropic and OpenAI-compatible APIs, plus scripted demo mode.</p></details>
          </>}
        </Card>
        <Card title="Make it sound like your business">
          <label className="block text-sm font-medium" htmlFor="assistant-tone">Reply style</label><textarea id="assistant-tone" rows={3} maxLength={1000} value={tone} onChange={(event) => { setTone(event.target.value); setSaved(false); }} className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" placeholder="Warm and professional. Keep replies short. Explain technical terms simply." />
          <p className="mt-2 text-xs leading-relaxed text-slate-500">Saved style is included in future AI reply prompts. Business facts and approval rules still govern what the assistant can offer.</p><div className="mt-3 flex items-center gap-3"><Button onClick={saveTone} disabled={saving || !tone.trim()}>{saving ? "Saving…" : "Save reply style"}</Button>{saved && <span role="status" className="text-xs text-emerald-700">Saved for future replies</span>}</div>
        </Card>
        <Card title="What makes this assistant yours">
          <p className="mb-3 text-sm font-medium">{business.tenant.name} <span className="font-normal text-slate-500">· {packName || business.tenant.pack_id}</span></p>
          <div className="space-y-3 text-sm"><div><p className="text-xs text-slate-500">Services</p><p className="mt-1">{business.settings.services?.map((service) => service.name).join(" · ") || "Add your services"}</p></div><div><p className="text-xs text-slate-500">Service areas</p><p className="mt-1">{business.settings.service_area?.join(", ") || "Add the areas you cover"}</p></div><div><p className="text-xs text-slate-500">Knowledge and availability</p><p className="mt-1">{business.settings.faqs?.length || 0} saved answers · {Object.keys(business.settings.business_hours || {}).length} opening days</p></div></div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs font-medium text-brand-700"><Link href="/settings#services" className="rounded-lg bg-brand-50 p-2.5">Edit services →</Link><Link href="/settings#answers" className="rounded-lg bg-brand-50 p-2.5">Add answers →</Link><Link href="/settings#hours" className="rounded-lg bg-brand-50 p-2.5">Opening hours →</Link><Link href="/settings#types" className="rounded-lg bg-brand-50 p-2.5">Booking questions →</Link></div>
          <p className="mt-3 text-xs leading-relaxed text-slate-500">Industry instructions guide intake and escalation. Your saved facts personalize replies; booking questions and approval rules control the workflow.</p>
        </Card>
      </div>
    </div>}
    {business && <WebsiteChatSetup key={business.tenant.slug} origins={business.settings.widget_origins || []} snippet={snippet} onSave={async (origins) => {
      const current = await api<Business>("/settings");
      const result = await put<Business>("/settings", { settings: { ...current.settings, widget_origins: origins } });
      setBusiness(result);
      return result.settings.widget_origins || [];
    }} />}
  </div>;
}
