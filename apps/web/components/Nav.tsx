"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { exitTenant, getToken, setToken } from "@/lib/auth";

type Me = {
  email: string;
  role: string;
  acting: boolean;
  tenant: { slug: string; name: string; pack_id: string; status: string; plan: string; onboarded: boolean } | null;
};
type Pack = { name: string; vocabulary: Record<string, string>; dashboard: { labels: Record<string, string> } };

const LINKS = [
  ["/inbox", "Inbox"],
  ["/queue", "Work queue"],
  ["/approvals", "Approvals"],
  ["/contacts", "Contacts"],
  ["/schedule", "Schedule"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
  ["/onboarding", "Setup"],
  ["/billing", "Billing"],
];
export const TENANT_CHANGED = "novaxis:tenant-changed";
const OPERATOR_LINKS = [["/operator", "Tenants"]];

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
    const loadMe = () => api<Me>("/me").then(setMe).catch(() => router.replace("/login"));
    loadMe();
    // Pages that change the tenant (billing, setup) ask the menu to re-read it.
    window.addEventListener(TENANT_CHANGED, loadMe);
    api<Pack>("/pack").then(setPack).catch(() => null);
    const load = () => api<{ count: number }>("/approvals").then((d) => setAwaiting(d.count)).catch(() => null);
    load();
    const id = setInterval(load, 5000);
    return () => {
      clearInterval(id);
      window.removeEventListener(TENANT_CHANGED, loadMe);
    };
  }, [router]);

  // Operators start in the console; a new owner finishes setup before anything else.
  const console_ = me?.role === "operator" && !me.acting;
  useEffect(() => {
    if (!me) return;
    if (console_ && !path.startsWith("/operator")) router.replace("/operator");
    else if (me.role === "owner" && me.tenant && !me.tenant.onboarded && !path.startsWith("/onboarding")) router.replace("/onboarding");
  }, [me, console_, path, router]);
  const links = console_ ? OPERATOR_LINKS : LINKS;
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [path]);
  const exit = () => {
    exitTenant();
    router.replace("/operator");
    window.location.reload();
  };

  return (
    <>
      {/* Phones: a top bar with a menu button; the side menu opens below it. */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Novaxis Worker</div>
          <div className="truncate text-xs text-slate-500">{console_ ? "Operator console" : me?.tenant?.name ?? ""}</div>
          {me?.acting && <button className="text-xs text-amber-800 underline" onClick={exit}>Operator view: exit</button>}
        </div>
        <button aria-label="Menu" aria-expanded={menuOpen} className="flex items-center gap-2 rounded border border-slate-300 px-3 py-1.5 text-sm" onClick={() => setMenuOpen(!menuOpen)}>
          {awaiting > 0 && <span className="rounded-full bg-amber-500 px-2 text-xs text-white">{awaiting}</span>}
          {menuOpen ? "Close" : "Menu"}
        </button>
      </header>
    <aside className={`${menuOpen ? "flex" : "hidden"} w-full shrink-0 flex-col border-b border-slate-200 bg-white p-4 md:flex md:w-56 md:border-b-0 md:border-r`}>
      <div className="mb-6">
        <div className="text-sm font-semibold">Novaxis Worker</div>
        <div className="text-xs text-slate-500">{console_ ? "Operator console" : pack?.name ?? me?.tenant?.pack_id ?? ""}</div>
        {me?.acting && (
          <div className="mt-3 rounded bg-amber-100 p-2 text-xs text-amber-900" data-testid="acting-banner">
            Operator view of <strong>{me.tenant?.name}</strong>
            <button className="mt-1 block underline" onClick={exit}>Exit to console</button>
          </div>
        )}
        {!console_ && me?.tenant?.status === "trial" && <Link href="/billing" className="mt-2 inline-block rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">Free trial</Link>}
        {!console_ && me?.tenant?.status === "paused" && <Link href="/billing" className="mt-2 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Paused: billing</Link>}
      </div>
      <nav className="flex flex-col gap-1 text-sm">
        {links.map(([href, label]) => (
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
    </>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
