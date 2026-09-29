"use client";

import { Card, Empty, ErrorLine, PageTitle, Table, type Column } from "@/components/ui";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Row = { id: string; contact: { display_name: string | null }; last_message: { body: string } | null; awaiting: number; updated_at: string; columns: Record<string, string | null> };
type Queue = { buckets: { key: string; label: string; items: Row[] }[] };

const columns: Column<Row>[] = [
  { key: "contact", label: "Contact", render: (r) => r.contact.display_name ?? r.columns.name ?? "New visitor" },
  { key: "last", label: "Last message", render: (r) => r.last_message?.body ?? "" },
  { key: "awaiting", label: "Awaiting", render: (r) => (r.awaiting ? String(r.awaiting) : "") },
  { key: "updated", label: "Updated", render: (r) => ago(r.updated_at) },
];

export default function QueuePage() {
  const { data, error } = usePoll<Queue>("/work-queue");
  return (
    <div className="flex flex-col gap-4">
      <PageTitle>Work queue</PageTitle>
      <ErrorLine error={error} />
      {(data?.buckets ?? []).map((b) => (
        <Card key={b.key} title={<>{b.label}<span className="ml-2 font-normal text-slate-500">{b.items.length}</span></>}>
          <Table columns={columns} rows={b.items} href={(r) => `/conversations/${r.id}`} />
        </Card>
      ))}
      {data && !data.buckets.length && <Card><Empty>The queue is empty.</Empty></Card>}
    </div>
  );
}
