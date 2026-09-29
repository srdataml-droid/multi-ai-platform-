"use client";

import Link from "next/link";
import type { ReactNode } from "react";

type Tone = "slate" | "green" | "amber" | "red" | "blue";

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-800 ring-amber-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    blue: "bg-brand-50 text-brand-700 ring-brand-200",
  };
  return <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>{children}</span>;
}

export function Button({ children, onClick, tone = "primary", disabled, type = "button" }: { children: ReactNode; onClick?: () => void; tone?: "primary" | "secondary" | "danger"; disabled?: boolean; type?: "button" | "submit" }) {
  const tones: Record<string, string> = {
    primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700",
    secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    danger: "bg-white text-red-700 ring-1 ring-inset ring-red-200 hover:bg-red-50",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${tones[tone]}`}>
      {children}
    </button>
  );
}

export function Card({ title, children, actions, id }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <section id={id} className="scroll-mt-32 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:p-5">
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <div className="flex flex-wrap gap-2">{actions}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export function PageTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-xl font-semibold tracking-tight text-slate-900">{children}</h1>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ value, label, tone }: { value: ReactNode; label: ReactNode; tone?: "amber" }) {
  return (
    <div>
      <div className={`text-2xl font-semibold tabular-nums tracking-tight ${tone === "amber" ? "text-amber-600" : "text-slate-900"}`}>{value}</div>
      <div className="mt-0.5 text-xs text-slate-500">{label}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-slate-500">{children}</p>;
}

export type Column<T> = { key: string; label: string; render?: (row: T) => ReactNode };

// A table on wide screens; on phones each row becomes a small card of label: value lines
// (the same markup restyled, so nothing is rendered twice).
export function Table<T extends { id: string }>({ columns, rows, href, empty = "Nothing here yet." }: { columns: Column<T>[]; rows: T[]; href?: (row: T) => string; empty?: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="md:overflow-x-auto">
      <table className="block w-full text-sm md:table">
        <thead className="hidden md:table-header-group">
          <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
            {columns.map((c) => (
              <th key={c.key} className="py-2 pr-4 font-medium">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="flex flex-col gap-2 md:table-row-group">
          {rows.map((r) => (
            <tr key={r.id} className="flex flex-col gap-1 rounded-xl border border-slate-200 p-3 md:table-row md:rounded-none md:border-0 md:border-b md:border-slate-100 md:p-0 md:hover:bg-slate-50">
              {columns.map((c, i) => {
                const val = c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "");
                const blank = val === "" || val === null || val === undefined;
                return (
                  <td
                    key={c.key}
                    data-label={c.label}
                    className={`${blank ? "hidden" : "flex"} gap-3 md:table-cell md:py-2.5 md:pr-4 md:align-top ${i === 0 ? "font-medium" : !c.label ? "pt-1 md:pt-2.5" : "text-slate-700 before:w-28 before:shrink-0 before:text-xs before:leading-5 before:text-slate-500 before:content-[attr(data-label)] md:before:hidden"}`}
                  >
                    {i === 0 && href ? <Link className="text-brand-700 underline-offset-2 hover:underline" href={href(r)}>{val}</Link> : val}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-200">{error}</p> : null;
}
