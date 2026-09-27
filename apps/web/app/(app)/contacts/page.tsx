"use client";

import { useState } from "react";
import { Badge, Card, ErrorLine, Table, type Column } from "@/components/ui";
import { post } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Dupe = { id: string; display_name: string };
type Row = { id: string; display_name: string | null; phones: string[]; emails: string[]; consent: string | null; created_at: string; possible_duplicates: Dupe[] };

export default function ContactsPage() {
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { data, error, refresh } = usePoll<{ items: Row[] }>(`/contacts?q=${encodeURIComponent(q)}`, 10000);

  // Never automatic: a chat visitor can type anyone's number, so a person confirms.
  const merge = async (r: Row, d: Dupe) => {
    if (!confirm(`Merge "${r.display_name ?? "Unknown"}" into "${d.display_name}"? Their conversations and bookings move to ${d.display_name}.`)) return;
    setErr(null);
    try {
      await post(`/contacts/${r.id}/merge`, { into: d.id });
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const columns: Column<Row>[] = [
    {
      key: "display_name",
      label: "Name",
      render: (r) => (
        <span>
          {r.display_name ?? "Unknown"}
          {r.possible_duplicates.map((d) => (
            <span key={d.id} className="ml-2 inline-flex items-center gap-1 text-xs">
              <Badge tone="amber">same phone or email as {d.display_name}</Badge>
              <button data-testid="merge-contact" className="underline" onClick={() => merge(r, d)}>Merge</button>
            </span>
          ))}
        </span>
      ),
    },
    { key: "phones", label: "Phones", render: (r) => r.phones.join(", ") },
    { key: "emails", label: "Emails", render: (r) => r.emails.join(", ") },
    { key: "consent", label: "Consent", render: (r) => r.consent ?? "" },
    { key: "created_at", label: "First seen", render: (r) => ago(r.created_at) },
  ];

  return (
    <Card title="Contacts" actions={<input className="rounded border border-slate-300 px-2 py-1 text-sm" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />}>
      <ErrorLine error={error ?? err} />
      <Table columns={columns} rows={data?.items ?? []} />
    </Card>
  );
}
