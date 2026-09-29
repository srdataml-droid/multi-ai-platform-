"use client";

import { Button, Card } from "@/components/ui";
import { keyFor } from "@/lib/bookingTypes";

export type Question = { key: string; ask: string; type: string; choices: string[]; required: boolean; sensitive?: boolean };
export type BookingType = { name: string; who: "anyone" | "new" | "existing"; service_code: string; questions: Question[] };
type Service = { code: string; name: string };

const WHO: [BookingType["who"], string][] = [
  ["anyone", "Anyone"],
  ["new", "New customers only"],
  ["existing", "Existing customers only"],
];
const ANSWERS: [string, string][] = [
  ["text", "Words"],
  ["choice", "One option from a list"],
  ["yesno", "Yes or no"],
  ["phone", "Phone number"],
  ["email", "Email address"],
  ["postcode", "Postcode (checked against your area)"],
  ["window", "When they would like it"],
];

export function BookingTypesCard(props: {
  types: BookingType[];
  services: Service[];
  starter: BookingType | null;
  question: string;
  onChange: (types: BookingType[]) => void;
  onQuestion: (q: string) => void;
}) {
  const { types, services, starter, onChange } = props;
  const setType = (i: number, patch: Partial<BookingType>) => onChange(types.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const setQ = (i: number, qi: number, patch: Partial<Question>) => {
    const t = types[i];
    const qs = t.questions.map((q, j) => {
      if (j !== qi) return q;
      const next = { ...q, ...patch };
      if (patch.ask !== undefined) {
        const others = t.questions.filter((_, k) => k !== qi).map((x) => x.key);
        if (!q.key || q.key === keyFor(q.ask, others)) next.key = keyFor(patch.ask, others);
      }
      if (patch.type !== undefined && patch.type !== "choice") next.choices = [];
      return next;
    });
    setType(i, { questions: qs });
  };
  const move = (i: number, qi: number, by: number) => {
    const qs = [...types[i].questions];
    const to = qi + by;
    if (to < 0 || to >= qs.length) return;
    [qs[qi], qs[to]] = [qs[to], qs[qi]];
    setType(i, { questions: qs });
  };
  const blank = (): BookingType => ({
    name: "New booking type",
    who: "anyone",
    service_code: services[0]?.code ?? "",
    questions: [{ key: "name", ask: "What's your name?", type: "text", choices: [], required: true }],
  });

  return (
    <Card title="Booking types">
      <p className="mb-2 text-sm text-slate-600">
        Different customers, different questions. None set: everyone gets the standard questions for your trade.
      </p>
      {types.length > 1 && (
        <label className="mb-3 block text-sm">
          <span className="text-slate-500">Asked first when more than one type fits the customer</span>
          <input className="mt-1 w-full rounded border border-slate-300 px-2 py-1" value={props.question} onChange={(e) => props.onQuestion(e.target.value)} />
        </label>
      )}
      {types.map((t, i) => (
        <div key={i} className="mb-3 rounded border border-slate-200 p-3 text-sm" data-testid={`booking-type-${i}`}>
          <div className="grid gap-2 sm:grid-cols-3">
            <label>
              <span className="text-slate-500">Name customers see</span>
              <input data-testid={`type-name-${i}`} className="mt-1 w-full rounded border px-2 py-1" value={t.name} onChange={(e) => setType(i, { name: e.target.value })} />
            </label>
            <label>
              <span className="text-slate-500">Who can book it</span>
              <select className="mt-1 w-full rounded border px-1 py-1" value={t.who} onChange={(e) => setType(i, { who: e.target.value as BookingType["who"] })}>
                {WHO.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label>
              <span className="text-slate-500">Books this service</span>
              <select className="mt-1 w-full rounded border px-1 py-1" value={t.service_code} onChange={(e) => setType(i, { service_code: e.target.value })}>
                {services.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </label>
          </div>
          <p className="mb-1 mt-3 font-medium">What we ask first</p>
          {t.questions.map((q, qi) => (
            <div key={qi} className="mb-1 flex flex-wrap items-center gap-2">
              <input aria-label="Question" className="min-w-[14rem] flex-1 rounded border px-2 py-1" value={q.ask} onChange={(e) => setQ(i, qi, { ask: e.target.value })} />
              <select aria-label="Answer" className="rounded border px-1 py-1" value={q.type} onChange={(e) => setQ(i, qi, { type: e.target.value })}>
                {ANSWERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              {q.type === "choice" && (
                <input aria-label="Options" placeholder="Options, comma separated" className="w-56 rounded border px-2 py-1" value={q.choices.join(", ")} onChange={(e) => setQ(i, qi, { choices: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
              )}
              <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={q.required} onChange={(e) => setQ(i, qi, { required: e.target.checked })} />needed</label>
              <label className="flex items-center gap-1 text-xs" title="Health, money and other private details: encrypted, hidden from viewers and from your own agent"><input type="checkbox" data-testid={`private-${i}-${qi}`} checked={!!q.sensitive} onChange={(e) => setQ(i, qi, { sensitive: e.target.checked })} />private</label>
              <button className="text-xs text-slate-500" aria-label="Move up" onClick={() => move(i, qi, -1)}>↑</button>
              <button className="text-xs text-slate-500" aria-label="Move down" onClick={() => move(i, qi, 1)}>↓</button>
              <button className="text-xs text-red-600" onClick={() => setType(i, { questions: t.questions.filter((_, j) => j !== qi) })}>remove</button>
            </div>
          ))}
          <div className="mt-2 flex gap-3">
            <button className="text-xs font-medium text-brand-700" onClick={() => setType(i, { questions: [...t.questions, { key: "", ask: "", type: "text", choices: [], required: true }] })}>Add a question</button>
            <button className="text-xs text-red-600" onClick={() => onChange(types.filter((_, j) => j !== i))}>Remove this booking type</button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button tone="secondary" onClick={() => onChange([...types, blank()])}>Add a booking type</Button>
        {starter && <Button tone="secondary" onClick={() => onChange([...types, { ...starter, name: types.length ? `${starter.name} ${types.length + 1}` : starter.name }])}>Start from our standard questions</Button>}
      </div>
      <p className="mt-3 text-xs text-slate-500"><b>Private</b>: encrypted and hidden from view-only staff and your own agent.</p>
    </Card>
  );
}
