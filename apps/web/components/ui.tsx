"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "blue" }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-emerald-100 text-emerald-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-800",
    blue: "bg-blue-100 text-blue-800",
  };
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Button({ children, onClick, tone = "primary", disabled, type = "button" }: { children: ReactNode; onClick?: () => void; tone?: "primary" | "secondary" | "danger"; disabled?: boolean; type?: "button" | "submit" }) {
  const tones: Record<string, string> = {
    primary: "bg-slate-900 text-white hover:bg-slate-700",
    secondary: "bg-white text-slate-900 border border-slate-300 hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`rounded px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${tones[tone]}`}>
      {children}
    </button>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          <div className="flex gap-2">{actions}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export type Column<T> = { key: string; label: string; render?: (row: T) => ReactNode };

export function Table<T extends { id: string }>({ columns, rows, href, empty = "Nothing here yet." }: { columns: Column<T>[]; rows: T[]; href?: (row: T) => string; empty?: string }) {
  if (!rows.length) return <p className="py-6 text-center text-sm text-slate-500">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            {columns.map((c) => (
              <th key={c.key} className="py-2 pr-4 font-medium">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
              {columns.map((c, i) => {
                const val = c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "");
                return (
                  <td key={c.key} className="py-2 pr-4 align-top">
                    {i === 0 && href ? <Link className="text-blue-700 underline-offset-2 hover:underline" href={href(r)}>{val}</Link> : val}
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
  return error ? <p className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null;
}
