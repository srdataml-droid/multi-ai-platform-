"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { exitTenant, getToken, setToken } from "@/lib/auth";
import { setBusinessTimeZone } from "@/lib/format";
import { every } from "@/lib/every";
import { type MenuLink, menuFor } from "@/lib/menu";
import { Icon, type IconName, Logo } from "@/components/icons";

type Me = {
  email: string;
  role: string;
  acting: boolean;
  tenant: { slug: string; name: string; pack_id: string; status: string; plan: string; onboarded: boolean; timezone: string; alerts_off: boolean } | null;
};
type Pack = { name: string; vocabulary: Record<string, string>; dashboard: { labels: Record<string, string> } };
type NavLink = MenuLink;

const ROLE_LABEL: Record<string, string> = { owner: "Owner", staff: "Team", viewer: "View only", operator: "Novaxis" };
export const TENANT_CHANGED = "novaxis:tenant-changed";

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [pack, setPack] = useState<Pack | null>(null);
  const [awaiting, setAwaiting] = useState(0);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    const loadMe = () =>
      api<Me>("/me")
        .then((m) => {
          setBusinessTimeZone(m.tenant?.timezone);
          setMe(m);
        })
        .catch(() => router.replace("/login"));
    loadMe();
    // Pages that change the tenant (billing, setup) ask the menu to re-read it.
    window.addEventListener(TENANT_CHANGED, loadMe);
    api<Pack>("/pack").then(setPack).catch(() => null);
    const load = () => api<{ count: number }>("/approvals").then((d) => setAwaiting(d.count)).catch(() => null);
    load();
    const stop = every(load, 5000);
    return () => {
      stop();
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
  useEffect(() => setMoreOpen(false), [path]);

  const role = me?.role ?? "";
  const links = menuFor(role, console_);
  const label = (l: NavLink) => (l.href === "/contacts" && pack?.vocabulary.customer ? cap(pack.vocabulary.customer) + "s" : l.label);
  const active = (l: NavLink) => path.startsWith(l.href);
  const tabs = links.slice(0, 4);
  const rest = links.slice(4);
  const place = console_ ? "Operator console" : me?.tenant?.name ?? "";

  const exit = () => {
    exitTenant();
    router.replace("/operator");
    window.location.reload();
  };
  const signOut = () => {
    setToken(null);
    router.replace("/login");
  };
  const count = (l: NavLink, testid?: string) =>
    l.href === "/approvals" && awaiting > 0 ? (
      <span data-testid={testid} className="min-w-5 rounded-full bg-amber-400 px-1.5 text-center text-[11px] font-semibold leading-5 text-amber-950">{awaiting > 99 ? "99+" : awaiting}</span>
    ) : null;

  const status =
    !console_ && me?.tenant?.status === "trial" ? (
      <Link href="/billing" className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">Free trial</Link>
    ) : !console_ && me?.tenant?.status === "paused" ? (
      <Link href="/billing" className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-200">Paused: billing</Link>
    ) : null;

  const acting = me?.acting ? (
    <div className="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900 ring-1 ring-inset ring-amber-200" data-testid="acting-banner">
      Operator view of <strong>{me.tenant?.name}</strong>
      <button className="mt-1 block font-medium underline" onClick={exit}>Exit to console</button>
    </div>
  ) : null;

  return (
    <>
      {/* Phones: a slim top bar, tabs at the bottom, the rest under "More". */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200/80 bg-white/90 px-4 py-2.5 backdrop-blur md:hidden">
        <Logo className="h-7 w-7 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{place || "Novaxis"}</div>
          {role && <div className="text-xs text-slate-500">{ROLE_LABEL[role] ?? role}</div>}
        </div>
        {status}
        {me?.acting && <button className="text-xs font-medium text-amber-800 underline" onClick={exit}>Exit</button>}
      </header>

      <nav aria-label="Main" className="pb-safe fixed inset-x-0 bottom-0 z-30 grid border-t border-slate-200 bg-white/95 backdrop-blur md:hidden" style={{ gridTemplateColumns: `repeat(${tabs.length + (rest.length ? 1 : 0)}, minmax(0, 1fr))` }}>
        {tabs.map((l) => (
          <Link key={l.href} href={l.href} aria-current={active(l) ? "page" : undefined} className={`relative flex flex-col items-center gap-0.5 pb-1.5 pt-2 text-[11px] font-medium ${active(l) ? "text-brand-700" : "text-slate-500"}`}>
            <Icon name={l.icon as IconName} className="h-6 w-6" />
            <span className="max-w-full truncate px-1">{label(l)}</span>
            {l.href === "/approvals" && awaiting > 0 && <span className="absolute left-1/2 top-1 ml-2 min-w-5 rounded-full bg-amber-400 px-1 text-center text-[10px] font-semibold leading-4 text-amber-950">{awaiting > 99 ? "99+" : awaiting}</span>}
          </Link>
        ))}
        {rest.length > 0 && (
          <button aria-expanded={moreOpen} onClick={() => setMoreOpen(true)} className={`flex flex-col items-center gap-0.5 pb-1.5 pt-2 text-[11px] font-medium ${rest.some(active) ? "text-brand-700" : "text-slate-500"}`}>
            <Icon name="more" className="h-6 w-6" />
            More
          </button>
        )}
      </nav>

      {rest.length > 0 && moreOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="More">
          <button aria-label="Close" className="absolute inset-0 bg-slate-900/40" onClick={() => setMoreOpen(false)} />
          <div className="pb-safe absolute inset-x-0 bottom-0 rounded-t-3xl bg-white p-4 shadow-2xl">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-200" />
            {acting && <div className="mb-3">{acting}</div>}
            <div className="grid grid-cols-3 gap-2">
              {rest.map((l) => (
                <Link key={l.href} href={l.href} className={`flex flex-col items-center gap-1.5 rounded-2xl p-3 text-xs font-medium ${active(l) ? "bg-brand-50 text-brand-700" : "bg-slate-50 text-slate-700"}`}>
                  <Icon name={l.icon as IconName} className="h-6 w-6" />
                  {label(l)}
                </Link>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
              <div className="min-w-0 text-xs">
                <div className="truncate font-medium text-slate-900">{me?.email}</div>
                <div className="text-slate-500">{ROLE_LABEL[role] ?? role}</div>
              </div>
              <button onClick={signOut} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300">
                <Icon name="out" className="h-4 w-4" /> Sign out
              </button>
            </div>
          </div>
        </div>
      )}

      {!console_ && me?.tenant?.alerts_off && (role === "owner" || role === "staff") && !path.startsWith("/settings") && (
        <Link href="/settings" data-testid="alerts-off" className="mx-4 mt-3 block rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-200 md:fixed md:bottom-4 md:right-4 md:z-20 md:mx-0 md:mt-0 md:max-w-xs md:shadow-lg">
          <strong>Alerts are off.</strong> You only hear about customers while this page is open. Turn on →
        </Link>
      )}

      {/* Wider screens: a side menu. */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200/80 bg-white px-3 py-4 md:flex">
        <div className="mb-5 flex items-center gap-2.5 px-2">
          <Logo />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{place || "Novaxis"}</div>
            <div className="truncate text-xs text-slate-500">{console_ ? "Novaxis" : pack?.name ?? ""}</div>
          </div>
        </div>
        {(status || acting) && <div className="mb-4 flex flex-col items-start gap-2 px-2">{status}{acting}</div>}
        <nav aria-label="Main" className="flex flex-col gap-0.5 text-sm">
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={active(l) ? "page" : undefined} className={`flex items-center gap-3 rounded-lg px-2.5 py-2 font-medium ${active(l) ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
              <Icon name={l.icon as IconName} className="h-[18px] w-[18px]" />
              <span className="flex-1">{label(l)}</span>
              {count(l, "approvals-badge")}
            </Link>
          ))}
        </nav>
        <div className="mt-auto flex items-center gap-2.5 rounded-xl border border-slate-200/80 p-2.5">
          <div aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold uppercase text-slate-600">{me?.email.charAt(0) ?? ""}</div>
          <div className="min-w-0 flex-1 text-xs">
            <div className="truncate font-medium text-slate-900">{me?.email}</div>
            <div className="text-slate-500">{ROLE_LABEL[role] ?? role}</div>
          </div>
          <button onClick={signOut} aria-label="Sign out" title="Sign out" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
            <Icon name="out" className="h-4 w-4" />
          </button>
        </div>
      </aside>
    </>
  );
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
