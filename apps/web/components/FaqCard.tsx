"use client";

import { Button, Card } from "@/components/ui";

export type Faq = { question: string; answer: string };

// The business's own answers. The assistant states facts about the business only from
// these and the settings above; a reply claiming anything else is held back and the
// question goes to staff (turn.fact_check).
export function FaqCard({ faqs, onChange }: { faqs: Faq[]; onChange: (f: Faq[]) => void }) {
  const set = (i: number, patch: Partial<Faq>) => onChange(faqs.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  return (
    <Card title="What customers ask">
      <p className="mb-3 text-sm text-slate-600">
        The assistant only states facts you give it. Anything else comes to you instead of being made up.
      </p>
      {faqs.map((f, i) => (
        <div key={i} className="mb-2 grid gap-2 rounded-xl border border-slate-200 p-2 text-sm sm:grid-cols-[1fr_2fr_auto] sm:items-center" data-testid={`faq-${i}`}>
          <input aria-label="Question" placeholder="Are your engineers Gas Safe registered?" value={f.question} onChange={(e) => set(i, { question: e.target.value })} />
          <input aria-label="Your answer" placeholder="Yes, all of them. Our registration number is 123456." value={f.answer} onChange={(e) => set(i, { answer: e.target.value })} />
          <button className="justify-self-end px-1 text-xs font-medium text-red-600" onClick={() => onChange(faqs.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <Button tone="secondary" onClick={() => onChange([...faqs, { question: "", answer: "" }])}>Add a question and answer</Button>
    </Card>
  );
}
