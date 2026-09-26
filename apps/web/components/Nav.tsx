"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getToken, setToken } from "@/lib/auth";

type Me = { email: string; role: string; tenant: { slug: string; pack_id: string } | null };
type Pack = { name: string; vocabulary: Record<string, string>; dashboard: { labels: Record<string, string> } };

const LINKS = [
  ["/inbox", "Inbox"],
  ["/queue", "Work queue"],
  ["/approvals", "Approvals"],
  ["/contacts", "Contacts"],
  ["/schedule", "Schedule"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
];

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [pack, setPack] = useState<Pack | null>(null);
  const [awaiting, setAwaiting] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Me>("/me").then(setMe).catch(() => router.replace("/login"));
    api<Pack>("/pack").then(setPack).catch(() => null);
    const load = () => api<{ count: number }>("/approvals").then((d) => setAwaiting(d.count)).catch(() => null);
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [router]);

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white p-4">
      <div className="mb-6">
        <div className="text-sm font-semibold">Novaxis Worker</div>
        <div className="text-xs text-slate-500">{pack?.name ?? me?.tenant?.pack_id ?? ""}</div>
      </div>
      <nav className="flex flex-col gap-1 text-sm">
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} className={`flex items-center justify-between rounded px-2 py-1.5 ${path.startsWith(href) ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}>
            <span>{label === "Contacts" && pack?.vocabulary.customer ? cap(pack.vocabulary.customer) + "s" : label}</span>
            {href === "/approvals" && awaiting > 0 && <span data-testid="approvals-badge" className="rounded-full bg-amber-500 px-2 text-xs text-white">{awaiting}</span>}
          </Link>
        ))}
      </nav>
      <div className="mt-auto pt-6 text-xs text-slate-500">
        <div>{me?.email}</div>
        <div className="capitalize">{me?.role}</div>
        <button className="mt-2 underline" onClick={() => { setToken(null); router.replace("/login"); }}>Sign out</button>
      </div>
    </aside>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
