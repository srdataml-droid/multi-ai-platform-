"use client";

import { useEffect, useState } from "react";
import { Badge, Card, ErrorLine, PageTitle, Table, type Column } from "@/components/ui";
import { api, post } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Dupe = { id: string; display_name: string };
type Row = { id: string; display_name: string | null; phones: string[]; emails: string[]; consent: string | null; created_at: string; possible_duplicates: Dupe[] };

export default function ContactsPage() {
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { data, error, refresh } = usePoll<{ items: Row[] }>(`/contacts?q=${encodeURIComponent(q)}`, 10000);
  // "Patients" at a dental practice, "Customers" elsewhere: the trade's own word.
  const [noun, setNoun] = useState("Contacts");
  useEffect(() => {
    api<{ vocabulary: Record<string, string> }>("/pack")
      .then((p) => p.vocabulary.customer && setNoun(p.vocabulary.customer.charAt(0).toUpperCase() + p.vocabulary.customer.slice(1) + "s"))
      .catch(() => null);
  }, []);

  // Never automatic: a chat visitor can type anyone's number, so a person confirms.
  const merge = async (r: Row, d: Dupe) => {
    if (!confirm(`Merge "${r.display_name ?? "No name yet"}" into "${d.display_name}"? Their conversations and bookings move to ${d.display_name}.`)) return;
    setErr(null);
    try {
      await post(`/contacts/${r.id}/merge`, { into: d.id });
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  // For a customer's request for their data. The API allows owners only.
  const exportOne = async (r: Row) => {
    setErr(null);
    try {
      const data = await api<unknown>(`/contacts/${r.id}/export`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `customer-${r.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const erase = async (r: Row) => {
    const typed = prompt(`This permanently deletes ${r.display_name ?? "this customer"}, their messages, bookings and photos. Type ERASE to confirm.`);
    if (typed !== "ERASE") return;
    setErr(null);
    try {
      await post(`/contacts/${r.id}/erase`, { confirm: "ERASE" });
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
          {r.display_name ?? "No name yet"}
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
    {
      key: "data",
      label: "Their data",
      render: (r) => (
        <span className="flex gap-2 text-xs">
          <button className="underline" onClick={() => exportOne(r)}>Export</button>
          <button className="text-red-600 underline" onClick={() => erase(r)}>Erase</button>
        </span>
      ),
    },
  ];

  return (
    <>
      <PageTitle actions={<input type="search" aria-label="Search" className="w-44 sm:w-60" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />}>{noun}</PageTitle>
      <ErrorLine error={error ?? err} />
      <Card>
        <Table columns={columns} rows={data?.items ?? []} empty="Nobody yet." />
      </Card>
    </>
  );
}
