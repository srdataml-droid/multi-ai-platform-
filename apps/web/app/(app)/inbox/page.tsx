"use client";

import { Badge, Card, ErrorLine, Table, type Column } from "@/components/ui";
import { STATUS_LABEL, ago } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";

type Row = { id: string; channel: string; status: string; bucket: string; unread: number; awaiting: number; contact: { display_name: string | null }; last_message: { body: string; direction: string; at: string } | null; columns: Record<string, string | null>; updated_at: string };
type Inbox = { columns: { key: string; label: string }[]; items: Row[] };

export default function InboxPage() {
  const { data, error } = usePoll<Inbox>("/inbox");
  const columns: Column<Row>[] = [
    { key: "contact", label: "Contact", render: (r) => r.contact.display_name ?? "Unknown" },
    { key: "last", label: "Last message", render: (r) => <span className={r.unread ? "font-semibold" : ""}>{r.last_message?.body ?? ""}</span> },
    ...(data?.columns ?? []).map((c) => ({ key: c.key, label: c.label, render: (r: Row) => r.columns[c.key] ?? "" })),
    { key: "status", label: "Status", render: (r) => <Badge tone={r.status === "waiting_human" ? "red" : r.awaiting ? "amber" : "slate"}>{r.awaiting ? `${r.awaiting} awaiting` : STATUS_LABEL[r.status] ?? r.status}</Badge> },
    { key: "channel", label: "Channel" },
    { key: "updated", label: "Updated", render: (r) => ago(r.updated_at) },
  ];
  return (
    <Card title="Inbox">
      <ErrorLine error={error} />
      <Table columns={columns} rows={data?.items ?? []} href={(r) => `/conversations/${r.id}`} empty="No conversations yet. Send a message through the widget or a channel." />
    </Card>
  );
}
