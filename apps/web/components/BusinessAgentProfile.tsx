"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, put } from "@/lib/api";
import { Button, Card, ErrorLine } from "@/components/ui";

type Profile = {
  enabled: boolean; assistant_name: string; personality: string;
  business_details: string; pricing_policy: string; handoff_preferences: string;
};
type Template = {
  available: boolean; name?: string; version: string; personality?: string;
  purpose?: string; knowledge?: string; gaps?: string[];
  sources?: { title: string; url: string }[];
};
const empty: Profile = { enabled: false, assistant_name: "", personality: "", business_details: "", pricing_policy: "", handoff_preferences: "" };
const fields: { key: Exclude<keyof Profile, "enabled">; label: string; hint: string; max: number }[] = [
  { key: "assistant_name", label: "Assistant name", hint: "Optional name used when introducing the AI assistant", max: 80 },
  { key: "personality", label: "Personality and reply preferences", hint: "How should it speak? Give a short example if useful.", max: 1500 },
  { key: "business_details", label: "Confirmed business knowledge", hint: "Your actual capabilities, equipment supported, policies and answers. Leave unknown facts blank.", max: 4000 },
  { key: "pricing_policy", label: "Fees and quotation policy", hint: "Only approved fees and terms; leave blank if staff must provide a quote.", max: 2000 },
  { key: "handoff_preferences", label: "Additional handoff preferences", hint: "When else should a person take over? Existing emergency and approval rules remain active.", max: 1500 },
];

export function BusinessAgentProfile() {
  const [template, setTemplate] = useState<Template | null>(null);
  const [profile, setProfile] = useState<Profile>(empty);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api<Template>("/settings/assistant-template"), api<{ settings: { assistant_profile?: Partial<Profile> } }>("/settings")])
      .then(([t, b]) => { if (active) { setTemplate(t); setProfile({ ...empty, ...b.settings.assistant_profile }); setLoaded(true); } })
      .catch((e) => { if (active) setError((e as Error).message); });
    return () => { active = false; };
  }, []);
  async function save(next: Profile, message: string, reset = false) {
    setSaving(true); setError(null); setNotice("");
    try {
      const current = await api<{ settings: Record<string, unknown> }>("/settings");
      if (reset) {
        const stored = (current.settings.assistant_profile || {}) as Partial<Profile>;
        next = { ...empty, ...stored, enabled: false, assistant_name: "", personality: "", handoff_preferences: "" };
      }
      await put("/settings", { settings: { ...current.settings, assistant_profile: next } });
      setProfile(next); setNotice(message); setEditing(false);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  return <Card title="Your industry agent template">
    <ErrorLine error={error} />
    {!loaded ? <p className="text-sm text-slate-500">{error ? "Template could not be loaded." : "Loading industry template…"}</p> : <div className="space-y-4">
      <div><p className="font-medium">{template?.name || "Industry template not yet researched"}</p><p className="mt-1 text-xs text-slate-500">Assigned from your business industry · template {template?.version}</p></div>
      <p className="text-sm">{template?.purpose || "Complete business facts in Settings. A new industry requires a reviewed template before it is offered."}</p>
      <div className="rounded-xl bg-slate-50 p-3 text-sm"><p className="font-medium">Industry background</p><p className="mt-1 text-slate-600">{template?.knowledge || "No reviewed industry background available."}</p><p className="mt-2 text-xs text-slate-500">Background is not proof that your company offers every service.</p></div>
      <details className="text-sm"><summary className="cursor-pointer font-medium">Defaults and operating rules</summary><p className="mt-2">Default personality: {template?.personality || "Friendly and brief"}</p><p className="mt-2">Collect the relevant intake details, use confirmed business facts, and route requests through the existing booking and approval tools. Never invent prices or available times. Industry emergency rules and permissions cannot be switched off here.</p><p className="mt-2 text-xs text-slate-500">SOUL: personality · AGENTS: operating rules · BUSINESS: verified facts. These are profile sections, not separate model training.</p></details>
      <div><p className="text-sm font-medium">Details only your business can confirm</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">{template?.gaps?.map((gap) => <li key={gap}>{gap}</li>)}</ul><div className="mt-3 flex flex-wrap gap-3 text-xs font-medium text-brand-700"><Link href="/settings#services">Services</Link><Link href="/settings#hours">Hours and availability</Link><Link href="/settings#types">Booking questions</Link><Link href="/settings#answers">FAQs</Link></div></div>
      <p className="text-xs text-slate-500">Opening hours do not prove a slot is free. Keep scheduling in your calendar and booking settings. Never add private customer or patient records to this shared business profile.</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={profile.enabled} disabled={!editing || saving} onChange={(e) => { setProfile({ ...profile, enabled: e.target.checked }); setNotice(""); }} />Use customised personality and handoff preferences</label>
      <p className="text-xs text-slate-500">Turning customisation off preserves your edits and uses industry behaviour with your existing reply style. Confirmed business facts remain available either way.</p>
      {fields.map(({ key, label, hint, max }) => <label key={key} className="block text-sm font-medium">{label}<textarea rows={key === "assistant_name" ? 1 : 3} maxLength={max} disabled={!editing || saving || (!profile.enabled && ["assistant_name", "personality", "handoff_preferences"].includes(key))} value={profile[key]} onChange={(e) => { setProfile({ ...profile, [key]: e.target.value }); setNotice(""); }} placeholder={hint} className="mt-1 w-full rounded-xl border border-slate-200 p-3 text-sm font-normal disabled:bg-slate-50" /><span className="mt-1 block text-xs font-normal text-slate-500">{hint}</span></label>)}
      <div className="flex flex-wrap gap-2"><Button tone="secondary" disabled={saving} onClick={() => setEditing(!editing)}>{editing ? "Lock editing" : "Enable editing"}</Button><Button disabled={!editing || saving} onClick={() => { void save(profile, "Profile saved for future replies."); }}>{saving ? "Saving…" : "Save profile"}</Button><Button tone="secondary" disabled={saving} onClick={() => { if (window.confirm("Restore default personality and handoff preferences? Your confirmed business facts, appointments and customer records will stay.")) void save({ ...profile, enabled: false, assistant_name: "", personality: "", handoff_preferences: "" }, "Default behaviour restored. Business facts kept.", true); }}>Restore defaults</Button></div>
      <p role="status" className="text-xs text-emerald-700">{notice}</p>
      <p className="text-xs text-slate-500">Editing lock protects against accidental edits in this screen; it is not an account permission. Conversation history remains separate. Persistent customer memory is not enabled by this profile.</p>
      <div className="flex flex-wrap gap-3 text-xs text-brand-700">{template?.sources?.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</div>
    </div>}
  </Card>;
}
