import type { ReactNode } from "react";
import { Logo } from "@/components/icons";

// The frame around sign in and sign up: brand at the top, one card, nothing else.
export function AuthShell({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="relative flex min-h-screen flex-col items-center overflow-hidden px-4 pb-10 pt-12 sm:justify-center sm:pt-10">
      <div aria-hidden="true" className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[40rem] -translate-x-1/2 rounded-full bg-brand-200/50 blur-3xl" />
      <div className="relative w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <Logo className="h-9 w-9" />
          <span className="text-lg font-semibold tracking-tight">Novaxis</span>
        </div>
        <section className="rounded-3xl border border-slate-200/80 bg-white p-5 shadow-xl shadow-slate-900/5 sm:p-6">
          <h1 className="mb-4 text-xl font-semibold tracking-tight">{title}</h1>
          {children}
        </section>
        {footer && <div className="mt-5 text-center text-sm text-slate-600">{footer}</div>}
      </div>
    </main>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700">
      {label}
      {children}
      {hint && <span className="text-xs font-normal text-slate-500">{hint}</span>}
    </label>
  );
}
