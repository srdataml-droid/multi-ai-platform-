"use client";

import { useState } from "react";
import { Button, Card, ErrorLine } from "@/components/ui";
import { websiteOrigins } from "@/lib/website-origins";

export function WebsiteChatSetup({ origins, snippet, onSave }: {
  origins: string[]; snippet: string; onSave: (origins: string[]) => Promise<string[]>;
}) {
  const [draft, setDraft] = useState(origins.join("\n"));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const result = await onSave(websiteOrigins(draft));
      setDraft(result.join("\n")); setSaved(true);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  };
  const copy = async () => {
    setError(null);
    try { await navigator.clipboard.writeText(snippet); setCopied(true); }
    catch { setError("Copy is unavailable in this browser. Select the code below and copy it manually."); }
  };
  return <Card id="website-install" title="Connect your website">
    <p className="text-sm leading-relaxed text-slate-600">This adds a Novaxis chat bubble to a website you own. Visitors chat there; you see their conversations in this business’s inbox. It creates its own chat interface and does not automatically connect an existing chatbot.</p>
    <div className="mt-5 grid gap-5 lg:grid-cols-2">
      <div>
        <h3 className="text-sm font-semibold">1. Choose the websites that can use your chat</h3>
        <p className="mt-2 text-xs leading-relaxed text-slate-500">Enter the address visitors open, such as https://www.yourbusiness.com. This is your business website, rather than the Novaxis dashboard. Use one address per line. Page paths are removed when you save.</p>
        <label htmlFor="studio-websites" className="mt-3 block text-sm font-medium">Your website addresses</label>
        <textarea id="studio-websites" rows={3} value={draft} onChange={(event) => { setDraft(event.target.value); setSaved(false); }} placeholder="https://www.yourbusiness.com" className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" />
        <p className="mt-2 text-xs text-slate-500">If visitors use both www and the address without www, add both. Your Novaxis dashboard can always show a preview.</p>
        <div className="mt-3 flex items-center gap-3"><Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save websites"}</Button>{saved && <span role="status" className="text-xs text-emerald-700">Website access saved</span>}</div>
        <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{origins.length ? `Saved access: ${origins.join(", ")}` : "No website restriction is saved. The chat can currently be used from any website."}</p>
      </div>
      <div>
        <h3 className="text-sm font-semibold">2. Add your business’s chat code</h3>
        <p className="mt-2 text-xs leading-relaxed text-slate-500">Copy the whole script tag into your website’s footer or custom-code area, just before the closing body tag. Install it once on each page where you want chat to appear.</p>
        {snippet ? <><pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{snippet}</pre><div className="mt-3"><Button tone="secondary" onClick={copy}>{copied ? "Code copied" : "Copy chat code"}</Button></div></> : <p className="mt-3 text-xs text-slate-500">Chat code is unavailable. Refresh the page or check the API connection.</p>}
        <h3 className="mt-5 text-sm font-semibold">3. Try it as a visitor</h3><p className="mt-2 text-xs leading-relaxed text-slate-500">Publish your website changes, open the website, and send a fictional enquiry through the chat bubble. Check Novaxis Inbox for the conversation. Saving an address alone does not install the code or prove the connection works.</p>
      </div>
    </div>
    <div className="mt-3"><ErrorLine error={error} /></div>
  </Card>;
}
