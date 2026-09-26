"use client";

import { useState } from "react";
import { Card, ErrorLine, Table, type Column } from "@/components/ui";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Row = { id: string; display_name: string | null; phones: string[]; emails: string[]; consent: string | null; created_at: string };
const columns: Column<Row>[] = [
  { key: "display_name", label: "Name", render: (r) => r.display_name ?? "Unknown" },
  { key: "phones", label: "Phones", render: (r) => r.phones.join(", ") },
  { key: "emails", label: "Emails", render: (r) => r.emails.join(", ") },
  { key: "consent", label: "Consent", render: (r) => r.consent ?? "" },
  { key: "created_at", label: "First seen", render: (r) => ago(r.created_at) },
];

export default function ContactsPage() {
  const [q, setQ] = useState("");
  const { data, error } = usePoll<{ items: Row[] }>(`/contacts?q=${encodeURIComponent(q)}`, 10000);
  return (
    <Card title="Contacts" actions={<input className="rounded border border-slate-300 px-2 py-1 text-sm" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />}>
      <ErrorLine error={error} />
      <Table columns={columns} rows={data?.items ?? []} />
    </Card>
  );
}
